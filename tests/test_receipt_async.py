"""
Leitura de nota por pedido.

A rota sincrona segurava a chamada enquanto o OCR rodava (44s medidos no
codigo em producao), e o app desistia em 45s mostrando "conexao interrompida".
Aqui a foto entra, volta um pedido na hora, e o app consulta ate ficar pronto.
"""

import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app import app
from app.auth.dependencies import get_current_user
from app.controller import receipt as rota
from app.schemas.receipt import ReceiptItem, ReceiptScanResponse

IMAGEM = {"image": ("nota.jpg", b"\xff\xd8\xff" + b"0" * 64, "image/jpeg")}

LIDA = ReceiptScanResponse(store="Mercado", total=10.0, items=[ReceiptItem(name="Leite", unit_price=5.0, quantity=2)])


class BaseAsync(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(rota._pedidos.clear)
        self._como(7)

    def _como(self, user_id: int):
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": user_id, "token": "t", "claims": {}, "teste": True,
        }

    def _enviar(self):
        resposta = self.client.post("/receipt/scan/async", files=IMAGEM)
        self.assertEqual(resposta.status_code, 202, resposta.text)
        return resposta.json()

    def _esperar(self, pedido_id: str, limite_s: float = 5.0) -> dict:
        fim = time.time() + limite_s
        while time.time() < fim:
            corpo = self.client.get(f"/receipt/scan/{pedido_id}").json()
            if corpo["status"] != "processando":
                return corpo
            time.sleep(0.02)
        self.fail("pedido nao terminou")


class TestFluxo(BaseAsync):
    def test_devolve_pedido_na_hora_e_resultado_depois(self):
        liberar = threading.Event()

        def lenta(*_):
            liberar.wait(5)
            return LIDA

        with patch.object(rota, "scan_receipt", side_effect=lenta):
            inicio = time.time()
            pedido = self._enviar()
            # A resposta nao espera o OCR.
            self.assertLess(time.time() - inicio, 2)
            self.assertEqual(pedido["status"], "processando")

            self.assertEqual(self.client.get(f"/receipt/scan/{pedido['pedido_id']}").json()["status"], "processando")

            liberar.set()
            final = self._esperar(pedido["pedido_id"])

        self.assertEqual(final["status"], "pronto")
        self.assertEqual(final["resultado"]["store"], "Mercado")
        self.assertEqual(final["resultado"]["items"][0]["name"], "Leite")

    def test_imagem_que_nao_e_nota_vira_erro_422(self):
        with patch.object(rota, "scan_receipt", side_effect=ValueError("not_a_receipt")):
            final = self._esperar(self._enviar()["pedido_id"])

        self.assertEqual((final["status"], final["codigo"]), ("erro", 422))
        self.assertIn("nota fiscal", final["detalhe"])

    def test_falha_inesperada_vira_erro_500_sem_derrubar_nada(self):
        with patch.object(rota, "scan_receipt", side_effect=RuntimeError("onnx caiu")):
            final = self._esperar(self._enviar()["pedido_id"])

        self.assertEqual((final["status"], final["codigo"]), ("erro", 500))

    def test_upload_invalido_e_recusado_antes_de_criar_pedido(self):
        resposta = self.client.post("/receipt/scan/async", files={"image": ("a.txt", b"oi", "text/plain")})

        self.assertEqual(resposta.status_code, 415)
        self.assertEqual(rota._pedidos, {})


class TestDono(BaseAsync):
    def test_outra_pessoa_nao_ve_o_pedido(self):
        with patch.object(rota, "scan_receipt", return_value=LIDA):
            pedido = self._enviar()
            self._esperar(pedido["pedido_id"])

        self._como(8)
        self.assertEqual(self.client.get(f"/receipt/scan/{pedido['pedido_id']}").status_code, 404)

    def test_pedido_inexistente_e_404(self):
        self.assertEqual(self.client.get("/receipt/scan/naoexiste").status_code, 404)

    def test_sem_autenticacao_e_401(self):
        app.dependency_overrides.clear()

        self.assertEqual(self.client.post("/receipt/scan/async", files=IMAGEM).status_code, 401)
        self.assertEqual(self.client.get("/receipt/scan/qualquer").status_code, 401)


class TestRecursos(BaseAsync):
    def test_nunca_duas_leituras_ao_mesmo_tempo(self):
        # Duas leituras juntas dobram o pico de RAM, e o servidor tem pouca.
        ativas = 0
        maximo = 0
        trava = threading.Lock()

        def contar(*_):
            nonlocal ativas, maximo
            with trava:
                ativas += 1
                maximo = max(maximo, ativas)
            time.sleep(0.1)
            with trava:
                ativas -= 1
            return LIDA

        with patch.object(rota, "scan_receipt", side_effect=contar):
            pedidos = [self._enviar()["pedido_id"] for _ in range(3)]
            self.client.post("/receipt/scan", files=IMAGEM)
            for pedido_id in pedidos:
                self.assertEqual(self._esperar(pedido_id)["status"], "pronto")

        self.assertEqual(maximo, 1)

    def test_pedido_vencido_some(self):
        with patch.object(rota, "scan_receipt", return_value=LIDA):
            antigo = self._enviar()["pedido_id"]
            self._esperar(antigo)

            with patch.object(rota, "VALIDADE_PEDIDO_S", 0):
                time.sleep(0.01)
                novo = self._enviar()["pedido_id"]

            self._esperar(novo)

        self.assertEqual(self.client.get(f"/receipt/scan/{antigo}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
