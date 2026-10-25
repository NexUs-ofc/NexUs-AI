"""Política de avaliação/retry sem chave real, chamadas externas ou bancos."""

import json
import unittest
from unittest.mock import Mock, patch

import httpx
from langchain_core.messages import AIMessage
from pymongo.errors import AutoReconnect, WTimeoutError
from sqlalchemy.exc import OperationalError

from app.auth import identidade
from app.core.judge import Verdict, deterministic_verdict, parse_verdict
from app.core.jev_client import JevClient, JevUnavailable
from app.core.provider_policy import TransientFallback, transient
from app.core.runtime_budget import BudgetExceeded, request_budget
from app.schemas import flow
from app.model.mongodb.recipe import Recipe
from app.repository.mongodb.recipes import RecipesRepository
from app.repository.pgsql.stock import StockRepository


def answer():
    return {"model": "jev-test", "answers": {
        "lastro": {"type": "choice", "choice": "apoiada", "confidence": 1,
                   "probabilities": {"apoiada": 1, "contradita": 0, "insuficiente": 0}},
        "fidelidade": {"type": "score", "score": 2, "confidence": 1,
                       "probabilities": {"0": 0, "1": 0, "2": 1}},
        "relevancia": {"type": "noul", "noul": 1},
        "segura": {"type": "noul", "noul": 1}}, "usage": {"input_tokens": 10, "output_tokens": 3}}


class ClientPolicyTest(unittest.TestCase):
    def make_client(self, handler, **kwargs):
        transport = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(transport.close)
        return JevClient("test-key", client=transport, jitter=lambda a, b: 0, **kwargs)

    def test_retry_after_transitorio_e_uma_segunda_tentativa(self):
        requests, now = [], [0]
        def handler(request):
            requests.append(request)
            return httpx.Response(429, headers={"Retry-After": "0.2"}) if len(requests) == 1 else httpx.Response(200, json=answer())
        client = self.make_client(handler, clock=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0] + n))
        self.assertIn("answers", client.evaluate({}, {}))
        self.assertEqual(len(requests), 2)
        self.assertEqual(now[0], 0.2)
        self.assertEqual(requests[0].headers["Authorization"], "Bearer test-key")

    def test_retry_after_maior_que_orcamento_nao_provoca_espera(self):
        handler = Mock(return_value=httpx.Response(429, headers={"Retry-After": "60"}))
        sleep = Mock()
        client = self.make_client(handler, budget=1, sleep=sleep)
        with self.assertRaises(JevUnavailable):
            client.evaluate({}, {})
        self.assertEqual(handler.call_count, 1)
        sleep.assert_not_called()

    def test_erros_permanentes_nao_sao_repetidos(self):
        for status in (400, 401, 403, 422, 302):
            with self.subTest(status=status):
                handler = Mock(return_value=httpx.Response(status))
                client = self.make_client(handler)
                with self.assertRaises(JevUnavailable) as raised:
                    client.evaluate({}, {})
                self.assertEqual(handler.call_count, 1)
                self.assertNotIn("test-key", str(raised.exception))

    def test_json_invalido_nao_e_repetido(self):
        handler = Mock(return_value=httpx.Response(200, content=b'not json'))
        client = self.make_client(handler)
        with self.assertRaises(JevUnavailable):
            client.evaluate({}, {})
        self.assertEqual(handler.call_count, 1)

    def test_circuit_breaker_abre_e_recupera_com_uma_sondagem(self):
        now, calls = [0], []
        def handler(request):
            calls.append(request)
            return httpx.Response(503) if len(calls) <= 3 else httpx.Response(200, json=answer())
        client = self.make_client(handler, attempts=1, clock=lambda: now[0])
        for _ in range(4):
            with self.assertRaises(JevUnavailable):
                client.evaluate({}, {})
        self.assertEqual(len(calls), 3)
        now[0] = 31
        self.assertIn("answers", client.evaluate({}, {}))
        self.assertEqual(len(calls), 4)

    def test_falha_de_transporte_tem_no_maximo_duas_tentativas(self):
        handler = Mock(side_effect=httpx.ReadTimeout("timeout"))
        client = self.make_client(handler, sleep=Mock())
        with self.assertRaises(JevUnavailable):
            client.evaluate({}, {})
        self.assertEqual(handler.call_count, 2)


class VerdictPolicyTest(unittest.TestCase):
    def test_fidelidade_e_relevancia_sao_avaliadas_separadamente(self):
        data = answer()
        data["answers"]["lastro"].update(choice="contradita", probabilities={"apoiada": 0, "contradita": 1, "insuficiente": 0})
        self.assertEqual(parse_verdict(data).decision, "repair")

    def test_apoio_confiavel_aprova(self):
        self.assertEqual(parse_verdict(answer()).decision, "approve")

    def test_resposta_relevante_mas_insegura_nao_aprova(self):
        data = answer()
        data["answers"]["segura"]["noul"] = 0.01
        self.assertEqual(parse_verdict(data).decision, "repair")

    def test_baixa_confianca_nao_aprova_automaticamente(self):
        data = answer()
        data["answers"]["lastro"]["confidence"] = 0.2
        self.assertEqual(parse_verdict(data).decision, "review")

    def test_evidencia_insuficiente_nao_vira_contradicao_por_relevancia_baixa(self):
        data = answer()
        data["answers"]["lastro"].update(choice="insuficiente", probabilities={"apoiada": 0, "contradita": 0, "insuficiente": 1})
        data["answers"]["relevancia"]["noul"] = 0.01
        self.assertEqual(parse_verdict(data).decision, "review")

    def test_score_invalido_ausente_ou_nao_finito_vira_revisao(self):
        for value in (float("nan"), float("inf"), True, -1, 3, "2"):
            with self.subTest(value=value):
                data = answer()
                data["answers"]["fidelidade"]["score"] = value
                self.assertEqual(parse_verdict(data).decision, "review")
        self.assertEqual(parse_verdict({}).decision, "review")

    def test_distribuicao_incoerente_nao_valida_score_alto(self):
        data = answer()
        data["answers"]["fidelidade"]["probabilities"] = {"0": 1, "1": 0, "2": 0}
        self.assertEqual(parse_verdict(data).decision, "review")

    def test_pedido_e_argumentos_nao_sao_recibo_de_execucao(self):
        envelope = {"intencao": "Criar evento", "resposta": "Criei o evento."}
        for evidence in ([], [{"ferramenta": "create_event", "conteudo": "null"}],
                         [{"ferramenta": "create_event", "conteudo": "false"}],
                         [{"ferramenta": "get_events", "conteudo": '[{"_id":"abc"}]'}]):
            with self.subTest(evidence=evidence):
                self.assertEqual(deterministic_verdict(envelope, evidence).decision, "repair")

    def test_retorno_confirmado_e_clarificacao_nao_sao_bloqueados(self):
        envelope = {"intencao": "Criar evento", "resposta": "Criei o evento."}
        self.assertIsNone(deterministic_verdict(envelope, [{"ferramenta": "create_event", "conteudo": '{"_id":"abc","title":"Jantar","household_id":124}'}]))
        self.assertIsNone(deterministic_verdict({**envelope, "esclarecer": "Qual data?"}, []))


class JudgeGraphTest(unittest.TestCase):
    def test_juiz_recebe_a_lista_renderizada_que_o_cliente_vai_ler(self):
        state = self.state()
        state["resposta_agente"] = json.dumps({"resposta": "Esta é sua lista.", "lista": {
            "title": "Compras", "array_list": [{"name": "Arroz", "quantity": 50,
                                                  "unitOfMeasure": "g", "checked": True}]}})
        with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
             patch.object(flow, "evaluate_jev", return_value=Verdict("approve")) as judge:
            flow.juiz(state)
        candidate = judge.call_args.args[1]
        self.assertIn("Arroz: 50 g (comprado)", candidate)
        self.assertNotIn("array_list", candidate)

    def test_projecoes_excluem_os_mesmos_ids_internos(self):
        record = {"_id": "list-internal", "household_id": 124, "title": "Compras", "array_list": [
            {"id": "item-internal", "foodId": 10, "name": "Arroz", "quantity": 50, "checked": True}]}
        evidence, _ = flow._compactar(json.dumps([record]))
        candidate = flow._para_o_juiz(json.dumps({"resposta": "Esta é sua lista.", "lista": record}))
        for internal in ("list-internal", "item-internal", "household_id", "foodId"):
            self.assertNotIn(internal, evidence)
            self.assertNotIn(internal, candidate)
        for factual in ("Arroz", "50", "checked"):
            self.assertIn(factual, evidence)
            self.assertIn(factual, candidate)

    def state(self):
        return {"trace_id": "test", "rota": "estoque", "mensagem": "O que tenho?", "historico": [],
                "resposta_agente": json.dumps({"resposta": "Estoque vazio."}),
                "evidencias": [{"ferramenta": "get_stock", "conteudo": "[]"}], "devolucoes": 0}

    def test_aprovacao_jev_dispensa_juiz_llm_e_redacao_extra(self):
        with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
             patch.object(flow, "evaluate_jev", return_value=Verdict("approve")), \
             patch.object(flow, "juiz_llm") as old, \
             patch.object(flow, "orquestrador_llm") as writer:
            state = flow.juiz(self.state())
            flow.orquestrador(state)
        old.invoke.assert_not_called()
        writer.invoke.assert_not_called()
        self.assertEqual(state["resposta_final"], "Estoque vazio.")

    def test_tokens_jev_nao_recebem_preco_do_llm(self):
        with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
             patch.object(flow, "evaluate_jev", return_value=Verdict("approve", input_tokens=100, output_tokens=10)):
            state = flow.juiz(self.state())
        self.assertEqual(state["input_tokens"], 0)
        self.assertEqual(state["judge_usage"]["input_tokens"], 100)

    def test_incerteza_escalada_uma_vez(self):
        with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
             patch.object(flow, "evaluate_jev", return_value=Verdict("review")), \
             patch.object(flow, "juiz_llm", Mock(invoke=Mock(return_value=AIMessage(content="VEREDITO: APROVADO\nMOTIVO:")))) as old:
            state = flow.juiz(self.state())
        self.assertTrue(state["juiz_aprovado"])
        self.assertEqual(old.invoke.call_count, 1)

    def test_indisponibilidade_e_formato_invalido_nao_aprovam(self):
        for content in (None, "texto inválido", "VEREDITO: DEVOLVER"):
            with self.subTest(content=content):
                args = {"side_effect": TimeoutError()} if content is None else {"return_value": AIMessage(content=content)}
                with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
                     patch.object(flow, "evaluate_jev", return_value=Verdict("review")), \
                     patch.object(flow, "juiz_llm", Mock(invoke=Mock(**args))):
                    state = flow.juiz(self.state())
                    flow.orquestrador(state)
                self.assertFalse(state["juiz_aprovado"])
                self.assertIn("Não consegui confirmar", state["resposta_final"])

    def test_nao_solicita_jev_para_confirmacao_sem_recibo(self):
        state = self.state()
        state["resposta_agente"] = json.dumps({"intencao": "Criar evento", "resposta": "Criei seu evento."})
        with patch.object(flow, "evaluate_jev") as judge:
            state = flow.juiz(state)
        judge.assert_not_called()
        self.assertTrue(state["veredito_juiz"])

    def test_segunda_reprovacao_encerra_sem_loop(self):
        state = self.state()
        state["devolucoes"] = 1
        with patch.object(flow, "JUDGE_PROVIDER", "jev"), \
             patch.object(flow, "evaluate_jev", return_value=Verdict("repair", "Corrija.")):
            flow.juiz(state)
        self.assertTrue(state["limite_devolucoes"])
        self.assertEqual(state["veredito_juiz"], "")

    def test_abstinencia_fixa_nao_chama_outro_revisor(self):
        state = self.state()
        state["limite_devolucoes"] = True
        flow.orquestrador(state)
        with patch.object(flow, "checar_saida", return_value={"conteudo": state["resposta_final"]}) as reviewer:
            flow.guardrail_saida(state)
        self.assertFalse(reviewer.call_args.kwargs["revisar"])


class RetrySideEffectTest(unittest.TestCase):
    def test_conexao_sql_perdida_no_commit_nao_reexecuta_remocao(self):
        session = Mock()
        session.commit.side_effect = OperationalError("COMMIT", {}, RuntimeError("conexão perdida"))
        repository = StockRepository(session)
        with identidade.da_requisicao(124, 124):
            for _ in range(2):
                self.assertIsNone(identidade.executar_gravacao("remove_product", {"id": 1}, lambda: repository.remove_product(Mock())))
            self.assertTrue(identidade.escrita_incerta())
        self.assertEqual(session.commit.call_count, 1)

    def test_mongo_sem_confirmacao_de_escrita_nao_cria_segunda_receita(self):
        for error in (AutoReconnect("perdeu conexão"), WTimeoutError("sem confirmação")):
            with self.subTest(error=type(error).__name__):
                collection = Mock()
                collection.insert_one.side_effect = error
                recipe = Recipe("Arroz", 2, [], "Cozinhe.", 124)
                with identidade.da_requisicao(124, 124), patch.object(RecipesRepository, "recipes_collection", collection):
                    for _ in range(2):
                        self.assertIsNone(identidade.executar_gravacao("salvar_receita", {"title": "Arroz"}, lambda: RecipesRepository.create_recipe(recipe)))
                    self.assertTrue(identidade.escrita_incerta())
                self.assertEqual(collection.insert_one.call_count, 1)

    def test_orcamento_global_impede_chamadas_extras_ao_modelo(self):
        primary = Mock()
        primary.timeout = 1
        primary.invoke.return_value = "ok"
        caller = TransientFallback(primary, None)
        with request_budget(seconds=10, calls=2):
            self.assertEqual(caller.invoke("a"), "ok")
            self.assertEqual(caller.invoke("b"), "ok")
            with self.assertRaises(BudgetExceeded):
                caller.invoke("c")
        self.assertEqual(primary.invoke.call_count, 2)

    def test_nao_inicia_chamada_que_nao_cabe_no_orcamento_restante(self):
        primary = Mock()
        primary.timeout = 3
        now = [0]
        caller = TransientFallback(primary, None)
        with request_budget(seconds=5, clock=lambda: now[0]):
            now[0] = 4
            with self.assertRaises(BudgetExceeded):
                caller.invoke("a")
        primary.invoke.assert_not_called()

    def test_provedores_esgotados_retornam_resposta_controlada_sem_500(self):
        class Exhausted(Exception):
            status_code = 429
        with patch.object(flow.ConversationsRepository, "pertence_conta", return_value=True), \
             patch.object(flow.ConversationsRepository, "sessao_ativa", return_value=True), \
             patch.object(flow.ConversationsRepository, "get_historico", return_value=[]), \
             patch.object(flow.ConversationsRepository, "append_messages"), \
             patch.object(flow, "em_segundo_plano"), \
             patch.object(flow.ceris_workflow, "invoke", side_effect=Exhausted()):
            result = flow.executar_chat("Qual meu estoque?", "6add00000000000000000124", 124, 124)
        self.assertIn("temporariamente indisponível", result["resposta"])
        self.assertIn("confira os registros", result["resposta"])

    def test_reparo_nao_refaz_escritas_com_argumentos_diferentes(self):
        action = Mock(return_value=True)
        with identidade.da_requisicao(124, 124):
            identidade.executar_gravacao("create_event", {"title": "A"}, action)
            with identidade.reparo_de_resposta():
                self.assertTrue(identidade.executar_gravacao("create_event", {"title": "A"}, action))
                self.assertIsNone(identidade.executar_gravacao("create_event", {"title": "B"}, action))
        self.assertEqual(action.call_count, 1)

    def test_ack_perdido_nao_repete_operacao(self):
        action = Mock(side_effect=TimeoutError("pode ter sido gravado"))
        with identidade.da_requisicao(124, 124):
            self.assertIsNone(identidade.executar_gravacao("create_list", {"title": "A"}, action))
            self.assertTrue(identidade.escrita_incerta())
            self.assertIsNone(identidade.executar_gravacao("create_list", {"title": "A"}, action))
        self.assertEqual(action.call_count, 1)

    def test_reparos_compartilham_um_limite_e_requisicoes_nao(self):
        with identidade.da_requisicao(124, 124):
            self.assertTrue(identidade.reservar_reparo())
            self.assertFalse(identidade.reservar_reparo())
        with identidade.da_requisicao(125, 125):
            self.assertTrue(identidade.reservar_reparo())

    def test_consulta_cacheada_e_invalidada_depois_de_escrita(self):
        read = Mock(side_effect=["antes", "depois"])
        with identidade.da_requisicao(124, 124):
            self.assertEqual(identidade.consultar_uma_vez("stock", read), "antes")
            self.assertEqual(identidade.consultar_uma_vez("stock", read), "antes")
            identidade.executar_gravacao("remove_product", {"id": 1}, lambda: True)
            self.assertEqual(identidade.consultar_uma_vez("stock", read), "depois")
        self.assertEqual(read.call_count, 2)

    def test_falha_de_consulta_nao_fica_cacheada(self):
        read = Mock(side_effect=["FALHA: indisponível", "[]"])
        with identidade.da_requisicao(124, 124):
            identidade.consultar_uma_vez("stock", read)
            self.assertEqual(identidade.consultar_uma_vez("stock", read), "[]")

    def test_fallback_so_acontece_em_falha_transitoria(self):
        primary, reserve = Mock(), Mock()
        primary.invoke.side_effect = httpx.ReadTimeout("timeout")
        reserve.invoke.return_value = "ok"
        wrapped = TransientFallback(primary, reserve)
        self.assertEqual(wrapped.invoke("test"), "ok")
        self.assertEqual(reserve.invoke.call_count, 1)
        primary.invoke.side_effect = ValueError("schema inválido")
        with self.assertRaises(ValueError):
            wrapped.invoke("test")
        self.assertEqual(reserve.invoke.call_count, 1)
        self.assertFalse(transient(ValueError("schema")))
