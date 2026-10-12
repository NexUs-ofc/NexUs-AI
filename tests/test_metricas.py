"""
As agregações que alimentam o painel do admin.

O Mongo é trocado por um dublê: nada de rede. O que se testa aqui é a
aritmética e o formato, que é o que o painel consome.
"""

import copy
import unittest
from typing import ClassVar
from unittest.mock import patch

from pymongo.errors import PyMongoError

from app.repository.mongodb.metrics import (
    REQUISICOES_POR_USUARIO_SEMANA,
    MetricsRepository,
    _percentil,
)
from app.repository.mongodb.traces import TracesRepository


class TestPercentil(unittest.TestCase):
    def test_lista_vazia_e_zero(self):
        self.assertEqual(_percentil([], 95), 0.0)

    def test_um_elemento_e_ele_mesmo(self):
        self.assertEqual(_percentil([42.0], 50), 42.0)
        self.assertEqual(_percentil([42.0], 95), 42.0)

    def test_extremos(self):
        valores = [float(n) for n in range(1, 101)]

        self.assertEqual(_percentil(valores, 0), 1.0)
        self.assertEqual(_percentil(valores, 100), 100.0)

    def test_p95_pega_o_elemento_95_de_100(self):
        """Percentil por indice, sem interpolacao."""

        self.assertEqual(_percentil([float(n) for n in range(1, 101)], 95), 95.0)

    def test_nao_depende_da_ordem_de_entrada(self):
        baguncado = [50.0, 1.0, 99.0, 20.0, 3.0]
        ordenado = sorted(baguncado)

        self.assertEqual(_percentil(baguncado, 50), _percentil(ordenado, 50))

    def test_p95_e_maior_ou_igual_ao_p50(self):
        valores = [float(n % 37) for n in range(200)]

        self.assertGreaterEqual(_percentil(valores, 95), _percentil(valores, 50))


class TestResumoDeRequisicoes(unittest.TestCase):
    LINHAS: ClassVar[list[dict]] = [
        {
            "_id": "estoque",
            "requisicoes": 4,
            "erros": 1,
            "duracoes": [1000.0, 2000.0, 3000.0, 100000.0],
            "tokens_entrada": 400,
            "tokens_saida": 100,
            "custo_usd": 0.004,
            "chamadas_de_tool": 6,
        },
        {
            "_id": "saudacao",
            "requisicoes": 6,
            "erros": 0,
            "duracoes": [900.0] * 6,
            "tokens_entrada": 60,
            "tokens_saida": 30,
            "custo_usd": 0.0006,
            "chamadas_de_tool": 0,
        },
    ]

    def _resumo(self, linhas=None):
        """
        Copia profunda de proposito: `resumo` faz `pop` nos documentos que
        recebe. Com cursor real do pymongo cada leitura traz dicts novos, mas
        um fixture compartilhado seria consumido pelo primeiro teste.
        """

        dados = copy.deepcopy(self.LINHAS if linhas is None else linhas)

        with patch.object(MetricsRepository.metrics_collection, "aggregate",
                          return_value=iter(dados)):
            return MetricsRepository.resumo(24)

    def test_soma_as_requisicoes_de_todas_as_rotas(self):
        self.assertEqual(self._resumo()["requisicoes"], 10)

    def test_taxa_de_erro_global(self):
        self.assertEqual(self._resumo()["taxa_de_erro"], 0.1)

    def test_taxa_de_erro_por_rota(self):
        resumo = self._resumo()

        self.assertEqual(resumo["por_rota"]["estoque"]["taxa_de_erro"], 0.25)
        self.assertEqual(resumo["por_rota"]["saudacao"]["taxa_de_erro"], 0.0)

    def test_p95_separa_o_caso_ruim_da_media(self):
        """A media esconderia os 100s; o p95 e a experiencia de quem esperou."""

        estoque = self._resumo()["por_rota"]["estoque"]

        self.assertEqual(estoque["p95_ms"], 100000.0)
        self.assertLess(estoque["p50_ms"], estoque["p95_ms"])

    def test_duracoes_nao_vazam_para_a_saida(self):
        """Lista crua inteira no JSON do painel seria payload a toa."""

        self.assertNotIn("duracoes", self._resumo()["por_rota"]["estoque"])

    def test_custo_por_requisicao(self):
        resumo = self._resumo()

        self.assertAlmostEqual(resumo["custo_usd"], 0.0046, places=6)
        self.assertAlmostEqual(resumo["custo_por_requisicao_usd"], 0.00046, places=6)

    def test_projecao_cresce_com_os_usuarios(self):
        projecao = self._resumo()["projecao_semanal_usd"]

        self.assertIn("100_usuarios", projecao)
        self.assertIn("1000_usuarios", projecao)
        self.assertGreater(projecao["1000_usuarios"], projecao["100_usuarios"])

    def test_projecao_usa_a_constante_declarada(self):
        resumo = self._resumo()
        esperado = round(
            resumo["custo_por_requisicao_usd"] * 100 * REQUISICOES_POR_USUARIO_SEMANA, 2
        )

        self.assertEqual(resumo["projecao_semanal_usd"]["100_usuarios"], esperado)

    def test_janela_sem_dado_nao_divide_por_zero(self):
        resumo = self._resumo([])

        self.assertEqual(resumo["requisicoes"], 0)
        self.assertEqual(resumo["taxa_de_erro"], 0.0)
        self.assertEqual(resumo["custo_por_requisicao_usd"], 0.0)

    def test_rota_sem_nome_nao_some(self):
        linhas = [{"_id": None, "requisicoes": 1, "erros": 0, "duracoes": [5.0],
                   "tokens_entrada": 0, "tokens_saida": 0, "custo_usd": 0.0,
                   "chamadas_de_tool": 0}]

        self.assertIn("desconhecida", self._resumo(linhas)["por_rota"])

    def test_mongo_fora_devolve_vazio_em_vez_de_estourar(self):
        with patch.object(MetricsRepository.metrics_collection, "aggregate",
                          side_effect=PyMongoError("atlas pausado")):
            self.assertEqual(MetricsRepository.resumo(24), {})

    def test_a_janela_pedida_aparece_na_resposta(self):
        with patch.object(MetricsRepository.metrics_collection, "aggregate",
                          return_value=iter([])):
            self.assertEqual(MetricsRepository.resumo(168)["janela_horas"], 168)


class TestLatenciaPorNo(unittest.TestCase):
    LINHAS: ClassVar[list[dict]] = [
        {"_id": "roteador", "execucoes": 50, "duracoes": [400.0] * 50},
        {"_id": "juiz", "execucoes": 3, "duracoes": [500.0, 13000.0, 25000.0]},
        {"_id": "saudacao", "execucoes": 8, "duracoes": [0.4] * 8},
    ]

    def _linhas(self, dados=None):
        copia = copy.deepcopy(self.LINHAS if dados is None else dados)

        with patch.object(TracesRepository.traces_collection, "aggregate",
                          return_value=iter(copia)):
            return TracesRepository.latencia_por_no(24)

    def test_ordena_pelo_p95_decrescente(self):
        """O primeiro da lista e onde mexer."""

        nos = [linha["no"] for linha in self._linhas()]

        self.assertEqual(nos[0], "juiz")

    def test_traz_execucoes_p50_p95_e_total(self):
        juiz = next(linha for linha in self._linhas() if linha["no"] == "juiz")

        self.assertEqual(juiz["execucoes"], 3)
        self.assertEqual(juiz["p50_ms"], 13000.0)
        self.assertEqual(juiz["p95_ms"], 25000.0)
        self.assertAlmostEqual(juiz["total_s"], 38.5, places=1)

    def test_no_sem_duracao_e_descartado(self):
        linhas = self._linhas([{"_id": "vazio", "execucoes": 0, "duracoes": []}])

        self.assertEqual(linhas, [])

    def test_no_sem_nome_nao_some(self):
        linhas = self._linhas([{"_id": None, "execucoes": 1, "duracoes": [1.0]}])

        self.assertEqual(linhas[0]["no"], "desconhecido")

    def test_mongo_fora_devolve_lista_vazia(self):
        with patch.object(TracesRepository.traces_collection, "aggregate",
                          side_effect=PyMongoError("atlas pausado")):
            self.assertEqual(TracesRepository.latencia_por_no(24), [])


if __name__ == "__main__":
    unittest.main()
