"""Regression tests for account-scoped sessions; no real database or model."""
import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId
from fastapi.testclient import TestClient

from app.app import app
from app.auth.dependencies import get_current_user
from app.auth import identidade
from app.controller import chat
from app.repository.mongodb.conversations import ConversationsRepository as Repo
from app.schemas import flow, memory


class Collection:
    def __init__(self, docs):
        self.docs = copy.deepcopy(docs)
        self.queries = []

    def find_one(self, query, *args, **kwargs):
        self.queries.append(query.copy())
        return next((copy.deepcopy(d) for d in self.docs
                     if all(d.get(k) == v for k, v in query.items())), None)

    def update_one(self, query, changes):
        self.queries.append(query.copy())
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(copy.deepcopy(changes.get("$set", {})))
                doc["historico"].extend(copy.deepcopy(
                    changes.get("$push", {}).get("historico", {}).get("$each", [])))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.own, self.other = ObjectId(), ObjectId()
        self.foreign_history = [{"role": "user", "content": "PRIVATE_125"},
                                {"role": "assistant", "content": "PRIVATE_REPLY_125"}]
        self.collection = Collection([
            {"_id": self.own, "account_id": 124, "historico": [], "updated_at": datetime.now(UTC)},
            {"_id": self.other, "account_id": 125, "historico": self.foreign_history},
        ])
        self.patch = patch.object(Repo, "conversations_collection", self.collection)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_foreign_session_cannot_be_read_or_authorized(self):
        self.assertFalse(Repo.pertence_conta(str(self.other), 124))
        self.assertFalse(Repo.sessao_ativa(str(self.other), 124))
        self.assertEqual(Repo.get_historico(str(self.other), 124), [])
        self.assertTrue(all(q["account_id"] == 124 for q in self.collection.queries))

    def test_foreign_session_cannot_be_changed(self):
        before = copy.deepcopy(self.collection.docs)
        Repo.append_messages(str(self.other), "attack", "answer", account_id=124)
        self.assertFalse(Repo.end_session(str(self.other), 124))
        self.assertEqual(self.collection.docs, before)
        self.assertTrue(all(q == {"_id": self.other, "account_id": 124}
                            for q in self.collection.queries))

    def test_owner_can_read_append_and_close(self):
        self.assertTrue(Repo.pertence_conta(str(self.own), 124))
        self.assertTrue(Repo.sessao_ativa(str(self.own), 124))
        Repo.append_messages(str(self.own), "hello", "reply", account_id=124,
                             receita={"titulo": "Rice"}, assunto={"tipo": "receita"})
        history = Repo.get_historico(str(self.own), 124)
        self.assertEqual(history[0]["content"], "hello")
        self.assertEqual(history[1]["receita"]["titulo"], "Rice")
        self.assertTrue(Repo.end_session(str(self.own), 124))
        self.assertFalse(Repo.sessao_ativa(str(self.own), 124))
        self.assertEqual(self.collection.docs[1]["historico"], self.foreign_history)

    def test_required_account_prevents_unscoped_calls(self):
        for method in (Repo.get_historico, Repo.sessao_ativa, Repo.end_session,
                       Repo.pertence_conta):
            with self.subTest(method=method.__name__), self.assertRaises(TypeError):
                method(str(self.own))
        with self.assertRaises(TypeError):
            Repo.append_messages(str(self.own), "hello", "reply")

    def test_invalid_ids_do_not_reach_database(self):
        for sid in ("string", "", "x" * 24):
            self.assertFalse(Repo.pertence_conta(sid, 124))
            self.assertFalse(Repo.sessao_ativa(sid, 124))
            self.assertFalse(Repo.end_session(sid, 124))
            self.assertEqual(Repo.get_historico(sid, 124), [])
            Repo.append_messages(sid, "hello", "reply", account_id=124)
        self.assertEqual(self.collection.queries, [])

    def test_direct_summary_cannot_copy_foreign_history(self):
        with patch.object(memory, "_gerar_resumo") as model, \
             patch.object(memory.MemoryRepository, "salvar_resumo") as save:
            self.assertEqual(memory.resumir_sessao(str(self.other), 124), "")
        model.assert_not_called()
        save.assert_not_called()

    def test_direct_memory_close_cannot_derive_foreign_preferences(self):
        with patch.object(memory, "_gerar_resumo") as model, \
             patch.object(memory, "derivar_preferencias") as derive, \
             patch.object(memory.MemoryRepository, "salvar_resumo") as save:
            result = memory.encerrar_sessao(str(self.other), 124, 124)
        self.assertEqual(result, {"resumo": "", "preferencias": []})
        model.assert_not_called()
        derive.assert_not_called()
        save.assert_not_called()

    def test_owner_summary_remains_supported(self):
        with patch.object(memory, "_gerar_resumo", return_value="summary") as model, \
             patch.object(memory.MemoryRepository, "salvar_resumo") as save:
            self.assertEqual(memory.resumir_sessao(str(self.other), 125), "summary")
        model.assert_called_once_with(self.foreign_history)
        self.assertEqual(save.call_args.kwargs["account_id"], 125)

    def test_concurrent_account_reads_remain_isolated(self):
        def probe(index):
            account = 124 if index % 2 else 125
            foreign = self.other if account == 124 else self.own
            owned = self.own if account == 124 else self.other
            return (Repo.get_historico(str(foreign), account),
                    Repo.pertence_conta(str(owned), account),
                    Repo.pertence_conta(str(foreign), account))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(probe, range(100)))
        self.assertTrue(all(r == ([], True, False) for r in results))

    def test_http_foreign_and_missing_sessions_return_404_before_models(self):
        previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_current_user] = lambda: {"user_id": 124}
        try:
            with patch.object(flow.ceris_workflow, "invoke") as graph, \
                 patch.object(chat, "encerrar_sessao") as close_memory, \
                 patch.object(Repo, "sessao_recente") as recent, \
                 TestClient(app) as client:
                for sid in (self.other, ObjectId()):
                    with self.subTest(session=str(sid)):
                        response = client.post("/chat/", json={
                            "mensagem": "Show the previous recipe",
                            "session_id": str(sid), "account_id": 125,
                            "household_account_id": 125,
                        })
                        self.assertEqual(response.status_code, 404)
                        response = client.delete("/chat/" + str(sid))
                        self.assertEqual(response.status_code, 404)
            graph.assert_not_called()
            close_memory.assert_not_called()
            recent.assert_not_called()
            self.assertEqual(self.collection.docs[1]["historico"], self.foreign_history)
            self.assertNotIn("ended_at", self.collection.docs[1])
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    def test_owner_close_passes_account_to_repository(self):
        with patch.object(chat, "encerrar_sessao", return_value={"resumo": "", "preferencias": []}) as close:
            result = chat.end_session(str(self.own), {"user_id": 124})
        self.assertTrue(result["encerrada"])
        close.assert_called_once_with(session_id=str(self.own), account_id=124, household_id=124)

    def test_legacy_invalid_session_placeholder_still_starts_owned_session(self):
        # Stop before the graph: verifies the existing Swagger fallback path.
        with patch.object(Repo, "sessao_recente", return_value=None) as recent, \
             patch.object(Repo, "create_session", side_effect=RuntimeError("stop")) as create:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                flow.executar_chat("Hello", "string", 124, 124)
        recent.assert_called_once_with(124)
        create.assert_called_once_with(124)

    def test_owner_chat_only_receives_and_updates_own_history(self):
        with patch.object(flow.ceris_workflow, "invoke", return_value={
            "resposta_final": "OWN_REPLY", "resposta_agente": "{}",
            "entrada_aprovada": True, "rota": "receitas",
        }) as graph, patch.object(flow, "em_segundo_plano"):
            result = flow.executar_chat("OWN_QUESTION", str(self.own), 124, 124)
        self.assertEqual(result["session_id"], str(self.own))
        state = graph.call_args.args[0]
        self.assertEqual(state["historico"], [])
        self.assertEqual(Repo.get_historico(str(self.own), 124)[0]["content"], "OWN_QUESTION")
        self.assertEqual(self.collection.docs[1]["historico"], self.foreign_history)

    def test_request_context_is_isolated_and_reset_even_after_exception(self):
        barrier = Barrier(2)
        def request(account):
            try:
                with identidade.da_requisicao(account, account, {"owner": account}):
                    barrier.wait(timeout=5)
                    self.assertEqual(identidade.perfil(), account)
                    self.assertEqual(identidade.conta(), account)
                    self.assertEqual(identidade.assunto(), {"owner": account})
                    raise ValueError("synthetic failure")
            except ValueError:
                pass
            with self.assertRaises(identidade.SemIdentidade):
                identidade.conta()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(request, (124, 125)))
