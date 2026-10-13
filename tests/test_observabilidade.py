"""
A fila que tira as escritas de telemetria do caminho da requisição.

Três propriedades que, se quebrarem, quebram em silêncio: não bloquear,
preservar a ordem e nunca propagar falha.
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.observability import background as bg

# Teto para esperar um Event: alto porque é rede de segurança contra travar a
# suíte, não medida de desempenho.
SEGUNDOS_DE_PACIENCIA = 5


class TestFilaDeObservabilidade(unittest.TestCase):
    def setUp(self):
        """Executor proprio por teste, para um nao contaminar o outro."""

        self.executor = ThreadPoolExecutor(max_workers=1)
        self.patch = patch.object(bg, "_executor", self.executor)
        self.patch.start()

        self.addCleanup(self.patch.stop)
        self.addCleanup(self.executor.shutdown, wait=True)

    def _esvaziar(self):
        self.executor.shutdown(wait=True)

    def test_nao_bloqueia_quem_chamou(self):
        """
        Sem cronômetro de propósito. A versão anterior exigia o retorno em
        menos de 0,1s e falhava dentro do container, onde subir a thread
        demora mais — media a máquina, não o código. Aqui a tarefa fica presa
        até ser solta: se a chamada esperasse por ela, `terminou` já estaria
        marcado quando a linha seguinte rodasse.
        """

        liberar = threading.Event()
        terminou = threading.Event()

        def presa():
            liberar.wait(SEGUNDOS_DE_PACIENCIA)
            terminou.set()

        bg.em_segundo_plano(presa)

        self.assertFalse(terminou.is_set(), "a escrita bloqueou a requisição")

        liberar.set()
        terminou.wait(SEGUNDOS_DE_PACIENCIA)

        self.assertTrue(terminou.is_set(), "a escrita nunca aconteceu")

    def test_a_escrita_realmente_acontece(self):
        feito = []

        bg.em_segundo_plano(feito.append, "gravado")
        self._esvaziar()

        self.assertEqual(feito, ["gravado"])

    def test_ordem_fifo_e_preservada(self):
        """
        A metrica da requisicao conta as tools lendo o Mongo, entao precisa
        rodar depois das escritas delas. A ordem e o que garante isso.
        """

        ordem = []

        def registrar(nome, espera):
            time.sleep(espera)
            ordem.append(nome)

        bg.em_segundo_plano(registrar, "tool_1", 0.05)
        bg.em_segundo_plano(registrar, "tool_2", 0.05)
        bg.em_segundo_plano(registrar, "metrica", 0.0)
        self._esvaziar()

        self.assertEqual(ordem, ["tool_1", "tool_2", "metrica"])

    def test_falha_de_telemetria_nao_propaga(self):
        def explode():
            raise RuntimeError("atlas pausado")

        bg.em_segundo_plano(explode)
        self._esvaziar()  # nao levanta

    def test_falha_de_uma_nao_impede_a_seguinte(self):
        feito = []

        def explode():
            raise RuntimeError("atlas pausado")

        bg.em_segundo_plano(explode)
        bg.em_segundo_plano(feito.append, "depois")
        self._esvaziar()

        self.assertEqual(feito, ["depois"])

    def test_argumentos_nomeados_chegam(self):
        recebido = {}

        def guardar(**kwargs):
            recebido.update(kwargs)

        bg.em_segundo_plano(guardar, trace_id="abc", duracao=1.5)
        self._esvaziar()

        self.assertEqual(recebido, {"trace_id": "abc", "duracao": 1.5})

    def test_roda_fora_da_thread_principal(self):
        onde = []

        bg.em_segundo_plano(lambda: onde.append(threading.current_thread().name))
        self._esvaziar()

        self.assertNotEqual(onde[0], threading.main_thread().name)


class TestFilaEncerrada(unittest.TestCase):
    def test_pool_encerrado_grava_em_linha(self):
        """Desligando o processo, a ultima escrita nao pode sumir."""

        morto = ThreadPoolExecutor(max_workers=1)
        morto.shutdown(wait=True)

        feito = []

        with patch.object(bg, "_executor", morto):
            bg.em_segundo_plano(feito.append, "ultima")

        self.assertEqual(feito, ["ultima"])


class TestAvisar(unittest.TestCase):
    def test_log_que_falha_nao_derruba_a_thread(self):
        """
        O pytest fecha o stdout capturado e o logging levanta
        "I/O operation on closed file" quando a escrita sai depois.
        """

        class LoggerQuebrado:
            def warning(self, *args, **kwargs):
                raise ValueError("I/O operation on closed file")

        with patch.object(bg, "logger", LoggerQuebrado()):
            bg.avisar("warning", "mensagem")  # nao levanta

    def test_nivel_inexistente_nao_levanta(self):
        bg.avisar("nivel_que_nao_existe", "mensagem")


if __name__ == "__main__":
    unittest.main()
