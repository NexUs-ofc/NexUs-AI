"""
As agregações da página da IA no painel do admin, e o que o grafo passou a
gravar para elas existirem: decisão do juiz e bloqueio dos guardrails.

Mongo, LangSmith e Groq entram como dublês: o que se testa é a aritmética e
o formato que o painel consome.
"""

import unittest
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas import flow, painel

FIM = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def metrica(rota="estoque", ms=1000.0, horas_atras=1, **extra):
    base = {
        "trace_id": extra.pop("trace_id", f"t-{rota}-{ms}-{horas_atras}"),
        "route": rota,
        "started_at": (FIM - timedelta(hours=horas_atras)).replace(tzinfo=None),
        "duration_ms": ms,
        "error": False,
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.001,
    }
    base.update(extra)
    return base


class TestResumo(unittest.TestCase):
    def test_numeros_do_topo(self):
        chat = [
            metrica(ms=1000, judge_decisions=["aprovado"]),
            metrica(ms=3000, error=True, judge_decisions=["devolvido", "aprovado"]),
            metrica(rota="faq", ms=500),
            metrica(rota="receitas", ms=9000, judge_decisions=["revertido"]),
        ]

        numeros = painel.resumo(chat, chat)

        self.assertEqual(numeros["execucoes"], 4)
        self.assertEqual(numeros["taxa_erro_pct"], 25.0)
        self.assertEqual(numeros["devolucoes_juiz_pct"], 25.0)
        self.assertEqual(numeros["custo_usd"], 0.004)
        self.assertEqual(numeros["p95_e2e_s"], 9.0)

    def test_sem_dado_e_zero_e_nao_erro(self):
        numeros = painel.resumo([], [])

        self.assertEqual(numeros["execucoes"], 0)
        self.assertEqual(numeros["taxa_erro_pct"], 0.0)
        self.assertEqual(numeros["devolucoes_juiz_pct"], 0.0)


class TestDesempenho(unittest.TestCase):
    def test_latencia_por_rota_ordena_pela_mais_lenta(self):
        linhas = painel.latencia_por_rota([
            metrica(rota="faq", ms=400),
            metrica(rota="receitas", ms=50000),
            metrica(rota="estoque", ms=20000),
        ])

        self.assertEqual([linha["rota"] for linha in linhas], ["receitas", "estoque", "faq"])
        self.assertEqual(linhas[0]["p95_s"], 50.0)

    def test_latencia_por_no_soma_as_etapas_por_execucao(self):
        chat = [metrica(rota="estoque", trace_id="a"), metrica(rota="estoque", trace_id="b")]
        spans = [
            {"trace_id": "a", "span_name": "roteador", "duration_ms": 1000},
            {"trace_id": "a", "span_name": "estoque", "duration_ms": 4000},
            {"trace_id": "a", "span_name": "estoque", "duration_ms": 2000},
            {"trace_id": "a", "span_name": "juiz", "duration_ms": 500},
            {"trace_id": "b", "span_name": "roteador", "duration_ms": 3000},
            {"trace_id": "b", "span_name": "guardrail_entrada", "duration_ms": 100},
            {"trace_id": "b", "span_name": "guardrail_saida", "duration_ms": 100},
            {"trace_id": "outro", "span_name": "roteador", "duration_ms": 99999},
        ]

        [linha] = painel.latencia_por_no(chat, spans)

        self.assertEqual(linha["rota"], "estoque")
        self.assertEqual(linha["execucoes"], 2)
        self.assertEqual(linha["etapas_s"]["roteador"], 2.0)
        self.assertEqual(linha["etapas_s"]["agente"], 3.0)
        self.assertEqual(linha["etapas_s"]["juiz"], 0.25)
        self.assertEqual(linha["etapas_s"]["guardrails"], 0.1)


class TestNota(unittest.TestCase):
    def test_conta_leituras_e_sucesso(self):
        notas = [
            metrica(rota="nota_fiscal", ms=1200),
            metrica(rota="nota_fiscal", ms=1600),
            metrica(rota="nota_fiscal", ms=800, error=True, error_type="not_a_receipt"),
        ]

        resultado = painel.leitura_nota(notas)

        self.assertEqual(resultado["leituras"], 3)
        self.assertEqual(resultado["sucesso"], 2)
        self.assertEqual(resultado["tempo_medio_s"], 1.2)

    def test_nota_nao_entra_no_volume_do_chat(self):
        metricas = [metrica(), metrica(rota="nota_fiscal")]

        self.assertEqual(len(painel._do_chat(metricas)), 1)


class TestCusto(unittest.TestCase):
    def test_tokens_por_dia_cobrem_a_janela_inteira(self):
        inicio = FIM - timedelta(days=3)
        metricas = [metrica(horas_atras=1), metrica(horas_atras=2), metrica(horas_atras=50)]

        tokens = painel.tokens_por_dia(metricas, inicio, FIM)

        self.assertEqual(len(tokens["dias"]), 4)
        self.assertEqual(tokens["total_entrada"], 300)
        self.assertEqual(tokens["pico"]["total"], 300)
        self.assertEqual(tokens["limite_diario"], 200_000)

    def test_custo_sem_modelo_cai_no_padrao(self):
        inicio = FIM - timedelta(days=1)
        custo = painel.custo_por_dia([metrica(), metrica(model="outro/modelo")], inicio, FIM)

        self.assertEqual(set(custo["por_modelo"]), {painel.MODELO_PADRAO, "outro/modelo"})

    def test_erros_de_cota_por_hora(self):
        metricas = [
            metrica(horas_atras=1, error=True, error_type="RateLimitError"),
            metrica(horas_atras=1, error=True, error_type="RateLimitError"),
            metrica(horas_atras=3, error=True, error_type="ValueError"),
            metrica(horas_atras=30, error=True, error_type="RateLimitError"),
        ]

        cota = painel.erros_de_cota(metricas, FIM)

        self.assertEqual(cota["total_24h"], 2)
        self.assertEqual(cota["total_janela"], 3)
        self.assertEqual(len(cota["por_hora"]), 24)


class TestQualidade(unittest.TestCase):
    def test_juiz_conta_cada_leitura(self):
        juiz = painel.juiz([
            metrica(judge_decisions=["aprovado"]),
            metrica(judge_decisions=["devolvido", "revertido"]),
            metrica(),
        ])

        self.assertEqual(juiz["total"], 3)
        self.assertEqual(juiz["aprovado"]["quantidade"], 1)
        self.assertEqual(juiz["devolvido"]["quantidade"], 1)
        self.assertEqual(juiz["revertido"]["quantidade"], 1)

    def test_guardrails_separa_entrada_e_saida(self):
        bloqueios = painel.guardrails([
            metrica(input_blocked=True),
            metrica(output_blocked=True),
            metrica(),
            metrica(),
        ])

        self.assertEqual(bloqueios["entrada"], 1)
        self.assertEqual(bloqueios["saida"], 1)
        self.assertEqual(bloqueios["pct"], 50.0)

    def test_ferramentas_por_volume(self):
        linhas = painel.ferramentas([
            {"tool_name": "get_stock", "duration_ms": 100, "success": True},
            {"tool_name": "get_stock", "duration_ms": 300, "success": False},
            {"tool_name": "tavily_search", "duration_ms": 900, "success": True},
        ])

        self.assertEqual(linhas[0]["tool"], "get_stock")
        self.assertEqual(linhas[0]["taxa_erro_pct"], 50.0)
        self.assertEqual(linhas[0]["media_ms"], 200.0)


class TestRelatorio(unittest.TestCase):
    def test_compara_com_o_periodo_anterior(self):
        atual = [metrica(), metrica(), metrica(error=True, judge_decisions=["devolvido"])]
        anterior = [metrica(horas_atras=200), metrica(horas_atras=200)]

        def listar(desde, ate):
            return atual if ate == FIM else anterior

        with patch.object(painel.MetricsRepository, "listar", side_effect=listar), \
             patch.object(painel.ToolMetricsRepository, "listar", return_value=[
                 {"tool_name": "get_stock", "duration_ms": 10, "success": False},
                 {"tool_name": "resolver_data", "duration_ms": 10, "success": True},
             ]):
            relatorio = painel.montar_relatorio(dias=7, fim=FIM)

        indicadores = {linha["indicador"]: linha for linha in relatorio["indicadores"]}

        self.assertEqual(indicadores["volume"]["atual"], 3)
        self.assertEqual(indicadores["volume"]["anterior"], 2)
        self.assertEqual(indicadores["volume"]["variacao"], 50.0)
        self.assertEqual(indicadores["taxa_erro_pct"]["variacao_em"], "pontos")
        self.assertEqual(indicadores["taxa_erro_pct"]["variacao"], 33.33)
        self.assertEqual([t["tool"] for t in relatorio["tools_com_mais_erro"]], ["get_stock"])

    def test_periodo_anterior_vazio_nao_divide_por_zero(self):
        with patch.object(painel.MetricsRepository, "listar", side_effect=lambda d, a: [metrica()] if a == FIM else []), \
             patch.object(painel.ToolMetricsRepository, "listar", return_value=[]):
            relatorio = painel.montar_relatorio(dias=7, fim=FIM)

        volume = next(linha for linha in relatorio["indicadores"] if linha["indicador"] == "volume")

        self.assertIsNone(volume["variacao"])


def _resposta(texto):
    return SimpleNamespace(content=texto, usage_metadata={"input_tokens": 10, "output_tokens": 5})


class TestJuizRegistraDecisao(unittest.TestCase):
    """O nó do juiz grava a decisão de cada leitura para o painel contar."""

    def _rodar(self, primeira):
        juiz_llm = MagicMock()
        juiz_llm.invoke.return_value = _resposta(primeira)
        estado = {
            "trace_id": "t", "rota": "estoque", "mensagem": "tenho arroz?", "historico": [],
            "evidencias": [], "resposta_agente": '{"resposta":"Consulta de estoque."}', "devolucoes": 0,
        }

        with patch.object(flow, "JUDGE_PROVIDER", "llm"), \
             patch.object(flow, "juiz_llm", juiz_llm), \
             patch.object(flow, "span", lambda *a, **k: nullcontext()):
            return flow.juiz.__wrapped__(estado)

    def test_aprovado_de_primeira(self):
        self.assertEqual(self._rodar("VEREDITO: APROVADO")["decisoes_juiz"], ["aprovado"])

    def test_formato_invalido_e_nao_confirmado(self):
        estado = self._rodar("resposta fora do contrato")
        self.assertEqual(estado["decisoes_juiz"], ["nao_confirmado"])

    def test_devolucao_confirmada(self):
        devolve = "VEREDITO: DEVOLVER\nMOTIVO: numero errado"
        estado = self._rodar(devolve)

        self.assertEqual(estado["decisoes_juiz"], ["devolvido"])



class TestEstadoDoGrafo(unittest.TestCase):
    """
    O LangGraph descarta entre os nós a chave que não está no schema do
    estado: sem declarar, a decisão do juiz sumia antes de chegar à métrica.
    """

    def test_campos_do_painel_estao_no_schema(self):
        from app.schemas.state import State

        self.assertIn("decisoes_juiz", State.__annotations__)
        self.assertIn("saida_bloqueada", State.__annotations__)

if __name__ == "__main__":
    unittest.main()
