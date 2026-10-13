"""
A porta do leitor de nota.

A rota ficou aberta desde que nasceu: qualquer um com a URL gastava OCR e três
chamadas de LLM por requisição, sem token nenhum. Estes testes existem para a
porta não cair de novo sem ninguém ver.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app import app
from app.auth.dependencies import get_current_user
from app.schemas.receipt import ReceiptScanResponse

IMAGEM = {"image": ("nota.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")}


class BaseReceipt(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

        self.addCleanup(app.dependency_overrides.clear)

    def _autenticar(self, user_id: int = 7):
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": user_id, "token": "t", "claims": {}, "teste": True,
        }


class TestExigeAutenticacao(BaseReceipt):
    def test_sem_credencial_nenhuma_e_401(self):
        self.assertEqual(self.client.post("/receipt/scan", files=IMAGEM).status_code, 401)

    def test_so_api_key_nao_basta(self):
        resposta = self.client.post(
            "/receipt/scan", files=IMAGEM, headers={"X-API-Key": "qualquer"},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_so_bearer_nao_basta(self):
        resposta = self.client.post(
            "/receipt/scan", files=IMAGEM, headers={"Authorization": "Bearer qualquer"},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_token_invalido_e_401(self):
        resposta = self.client.post(
            "/receipt/scan",
            files=IMAGEM,
            headers={"X-API-Key": "qualquer", "Authorization": "Bearer nao.e.um.jwt"},
        )

        self.assertEqual(resposta.status_code, 401)


class TestNaoGastaAntesDeAutenticar(BaseReceipt):
    """
    A ordem importa: autenticar depois de ler a imagem significa pagar OCR e
    modelo por quem nem devia ter entrado.
    """

    def test_nao_chama_o_pipeline_sem_token(self):
        with patch("app.controller.receipt.scan_receipt") as pipeline:
            self.client.post("/receipt/scan", files=IMAGEM)

        pipeline.assert_not_called()

    def test_recusa_antes_de_olhar_o_content_type(self):
        """Sem token, o 401 vem antes do 415 — a rota nem chega a validar."""

        resposta = self.client.post(
            "/receipt/scan",
            files={"image": ("nota.exe", b"MZ", "application/x-msdownload")},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_imagem_grande_sem_token_nao_e_processada(self):
        grande = {"image": ("nota.png", b"0" * (9 * 1024 * 1024), "image/png")}

        with patch("app.controller.receipt.scan_receipt") as pipeline:
            resposta = self.client.post("/receipt/scan", files=grande)

        self.assertEqual(resposta.status_code, 401)
        pipeline.assert_not_called()


class TestAutenticadoPassa(BaseReceipt):
    def test_com_token_o_pipeline_roda(self):
        self._autenticar()

        with patch("app.controller.receipt.scan_receipt",
                   return_value=ReceiptScanResponse(store="Mercado", source="ocr")) as pipeline:
            resposta = self.client.post("/receipt/scan", files=IMAGEM)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["store"], "Mercado")
        pipeline.assert_called_once()

    def test_o_formato_de_saida_continua_o_mesmo(self):
        """A autenticacao e uma porta, nao uma mudanca de contrato."""

        self._autenticar()

        with patch("app.controller.receipt.scan_receipt",
                   return_value=ReceiptScanResponse()):
            corpo = self.client.post("/receipt/scan", files=IMAGEM).json()

        self.assertEqual(set(corpo), set(ReceiptScanResponse.model_fields))

    def test_erros_de_imagem_continuam_valendo_depois_do_token(self):
        self._autenticar()

        casos = (
            ({"image": ("nota.exe", b"MZ", "application/x-msdownload")}, 415),
            ({"image": ("nota.png", b"", "image/png")}, 400),
            ({"image": ("nota.png", b"0" * (9 * 1024 * 1024), "image/png")}, 413),
        )

        for arquivo, esperado in casos:
            with self.subTest(status=esperado):
                self.assertEqual(
                    self.client.post("/receipt/scan", files=arquivo).status_code, esperado,
                )


class TestPerfilNaoVemDoCliente(BaseReceipt):
    """
    O `profile_id` chegava por formulario e nunca era usado. Deixar o cliente
    nomear o perfil e o contrario de restringir: quem manda e o `sub` do token,
    como ja acontece no /chat.
    """

    def test_a_rota_nao_declara_mais_profile_id(self):
        rota = self._rota_do_scan()
        campos = {campo.name for campo in rota.dependant.body_params}

        self.assertNotIn("profile_id", campos)

    def test_profile_id_no_corpo_e_ignorado(self):
        self._autenticar(user_id=7)

        with patch("app.controller.receipt.scan_receipt",
                   return_value=ReceiptScanResponse()):
            resposta = self.client.post(
                "/receipt/scan", files=IMAGEM, data={"profile_id": "999"},
            )

        self.assertEqual(resposta.status_code, 200)

    def test_a_dependencia_de_autenticacao_esta_declarada(self):
        """Regressao: a rota ja subiu sem nenhuma dependencia."""

        rota = self._rota_do_scan()
        chamadas = {dep.call for dep in rota.dependant.dependencies}

        self.assertIn(get_current_user, chamadas)

    def _rota_do_scan(self):
        """
        O FastAPI desta versao nao achata os routers incluidos em app.routes:
        guarda um _IncludedRouter com o router original dentro. Varrer os dois
        niveis mantem o teste de pe se um dia ele voltar a achatar.
        """

        from fastapi.routing import APIRoute

        pilha = list(app.routes)

        while pilha:
            rota = pilha.pop()

            if isinstance(rota, APIRoute) and rota.path == "/receipt/scan":
                return rota

            original = getattr(rota, "original_router", None)

            if original is not None:
                pilha.extend(original.routes)

        raise AssertionError("rota /receipt/scan nao encontrada")


if __name__ == "__main__":
    unittest.main()
