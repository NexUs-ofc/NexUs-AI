"""
Falha de consulta não pode virar "você não tem nada".

Aconteceu em produção: o repositório devolvia `[]` quando a query quebrava, a
tool dizia "o usuário não possui nenhum produto" e o modelo repassava isso
como fato — com 11 itens no banco. Nem juiz nem guardrail pegam, porque a
evidência em si está errada.
"""

import unittest
from typing import ClassVar
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from app.repository.pgsql.stock import ConsultaIndisponivel, StockRepository
from app.tools import pg_tools


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


if __name__ == "__main__":
    unittest.main()
