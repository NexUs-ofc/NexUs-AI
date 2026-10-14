"""
Falha de consulta não pode virar "você não tem nada".

Aconteceu em produção: o repositório devolvia `[]` quando a query quebrava, a
tool dizia "o usuário não possui nenhum produto" e o modelo repassava isso
como fato — com 11 itens no banco. Nem juiz nem guardrail pegam, porque a
evidência em si está errada.
"""

import logging
import unittest
from typing import ClassVar
from unittest.mock import patch

from qdrant_client.http.exceptions import ResponseHandlingException
from sqlalchemy.exc import OperationalError

from app.repository.pgsql.stock import ConsultaIndisponivel, StockRepository
from app.repository.qdrant.config import TEMPO_LIMITE_BUSCA_S
from app.tools import faq_tools, pg_tools


class TestRepositorioLevantaEmVezDeMentir(unittest.TestCase):
    def _sessao_que_quebra(self):
        class SessaoQuebrada:
            def scalars(self, *args, **kwargs):
                raise OperationalError("select", {}, Exception("conexao caiu"))

            def execute(self, *args, **kwargs):
                raise OperationalError("select", {}, Exception("conexao caiu"))

        return SessaoQuebrada()

    def test_get_stock_levanta(self):
        repo = StockRepository(self._sessao_que_quebra())

        with self.assertRaises(ConsultaIndisponivel):
            repo.get_stock(3)

    def test_get_expired_products_levanta(self):
        repo = StockRepository(self._sessao_que_quebra())

        with self.assertRaises(ConsultaIndisponivel):
            repo.get_expired_products(3)

    def test_get_missing_products_levanta(self):
        repo = StockRepository(self._sessao_que_quebra())

        with self.assertRaises(ConsultaIndisponivel):
            repo.get_missing_products(3)

    def test_a_excecao_diz_o_que_falhou(self):
        repo = StockRepository(self._sessao_que_quebra())

        with self.assertRaises(ConsultaIndisponivel) as ctx:
            repo.get_stock(3)

        self.assertIn("estoque", str(ctx.exception))

    def test_nao_e_confundida_com_erro_de_programacao(self):
        self.assertTrue(issubclass(ConsultaIndisponivel, RuntimeError))


class TestToolTraduzFalhaParaOModelo(unittest.TestCase):
    MENSAGENS_DE_VAZIO: ClassVar[tuple[str, ...]] = (
        "não possui nenhum produto",
        "Nenhum produto",
        "não há produtos",
    )

    def _falhando(self, metodo):
        return patch.object(
            pg_tools.StockRepository, metodo,
            side_effect=ConsultaIndisponivel("listar o estoque"),
        )

    def test_get_stock_avisa_que_falhou(self):
        with self._falhando("get_stock"):
            saida = pg_tools.get_stock.invoke({"profile_id": 3})

        self.assertTrue(saida.startswith("FALHA"))

    def test_a_mensagem_nega_explicitamente_que_esteja_vazio(self):
        """Sem isto o modelo le "falhou" e responde "voce nao tem nada"."""

        with self._falhando("get_stock"):
            saida = pg_tools.get_stock.invoke({"profile_id": 3})

        self.assertIn("NAO significa que esta vazio", saida)

    def test_falha_nao_se_parece_com_estoque_vazio(self):
        with self._falhando("get_stock"):
            saida = pg_tools.get_stock.invoke({"profile_id": 3}).lower()

        for frase in self.MENSAGENS_DE_VAZIO:
            with self.subTest(frase=frase):
                self.assertNotIn(frase.lower(), saida)

    def test_as_tres_leituras_tratam_a_falha(self):
        casos = (
            ("get_expired_products", pg_tools.get_expired_products),
            ("get_missing_products", pg_tools.get_missing_products),
        )

        for metodo, tool in casos:
            with self.subTest(tool=metodo):
                with self._falhando(metodo):
                    saida = tool.invoke({"profile_id": 3})

                self.assertTrue(saida.startswith("FALHA"), saida[:60])

    def test_a_tool_nao_propaga_a_excecao(self):
        """O agente precisa de texto para relatar, nao de um 500."""

        with self._falhando("get_stock"):
            pg_tools.get_stock.invoke({"profile_id": 3})


class TestBuscaNoQdrant(unittest.TestCase):
    """
    Mesma regra, outra fonte: o Qdrant estourava o tempo de leitura e a
    excecao subia da tool para o no, derrubando a pergunta inteira. Medido:
    a busca leva de 0,2s a 0,4s, mas um pico passava dos 5s do padrao do
    cliente.
    """

    TEMPO_ESGOTADO: ClassVar[Exception] = ResponseHandlingException(
        "The read operation timed out"
    )

    def _faq(self, **kwargs):
        return patch.object(faq_tools.faq_repo, "buscar_respostas_faq", **kwargs)

    def _doc(self, **kwargs):
        return patch.object(faq_tools.doc_repo, "buscar_trechos_documentacao", **kwargs)

    def setUp(self):
        logging.disable(logging.CRITICAL)

        self.addCleanup(logging.disable, logging.NOTSET)

    def test_as_duas_buscas_falhando_viram_aviso(self):
        with self._faq(side_effect=self.TEMPO_ESGOTADO), self._doc(side_effect=self.TEMPO_ESGOTADO):
            saida = faq_tools.faq_retriever.invoke({"question": "o que e o Ceris?"})

        self.assertTrue(saida.startswith("FALHA"))
        self.assertIn("NAO significa que a resposta nao existe", saida)

    def test_a_tool_nao_propaga_a_excecao(self):
        with self._faq(side_effect=self.TEMPO_ESGOTADO), self._doc(side_effect=self.TEMPO_ESGOTADO):
            faq_tools.faq_retriever.invoke({"question": "o que e o Ceris?"})

    def test_o_que_uma_busca_trouxe_vale_mais_que_o_alarme(self):
        """Com metade da evidencia em maos, avisar de falha seria pior."""

        with self._faq(side_effect=self.TEMPO_ESGOTADO), self._doc(return_value=["trecho do manual"]):
            saida = faq_tools.faq_retriever.invoke({"question": "o que e o Ceris?"})

        self.assertEqual(saida, "- trecho do manual")

    def test_nao_achar_nada_nao_e_falha(self):
        """Vazio por corte de similaridade continua vazio, como antes."""

        with self._faq(return_value=[]), self._doc(return_value=[]):
            saida = faq_tools.faq_retriever.invoke({"question": "xyz"})

        self.assertEqual(saida, "")

    def test_caminho_feliz_intacto(self):
        with self._faq(return_value=["resposta A", "resposta B"]), self._doc(return_value=["sobra"]):
            saida = faq_tools.faq_retriever.invoke({"question": "o que e o Ceris?"})

        self.assertEqual(saida, "- resposta A\n- resposta B")

    def test_a_documentacao_so_preenche_as_vagas_que_sobraram(self):
        with self._faq(return_value=["unica"]), self._doc(return_value=["do manual"]) as doc:
            saida = faq_tools.faq_retriever.invoke({"question": "o que e o Ceris?"})

        doc.assert_called_once()
        self.assertEqual(doc.call_args.kwargs["k"], 1)
        self.assertEqual(saida, "- unica\n- do manual")

    def test_as_buscas_tem_tempo_limite_maior_que_o_padrao(self):
        """O padrao do cliente e 5s; o pico que derrubava passava disso."""

        self.assertGreater(TEMPO_LIMITE_BUSCA_S, 5)

        for nome, repositorio in (("faq", faq_tools.faq_repo), ("doc", faq_tools.doc_repo)):
            with self.subTest(repositorio=nome):
                self.assertEqual(repositorio.client._client._timeout, TEMPO_LIMITE_BUSCA_S)


if __name__ == "__main__":
    unittest.main()
