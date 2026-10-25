"""Receita avulsa → evento com restrição → lista genérica, sem bancos reais."""

import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from bson import ObjectId
from langchain_core.messages import AIMessage

from app.auth import identidade
from app.core.contexto_conversa import assunto_do_turno, resolver_assunto, pedido_lista_generico
from app.model.mongodb.event import Event
from app.repository.mongodb.shopping_lists import ShoppingListsRepository
from app.repository.mongodb.conversations import ConversationsRepository
from app.schemas import flow
from app.tools import general_tools, mongodb_tools, recipe_tools


EGGS = {"titulo": "Ovos mexidos", "porcoes": 2,
        "ingredientes": [{"ingrediente": "Ovos", "quantidade_total": "2 unidades"}],
        "instrucoes": ["Mexa os ovos na frigideira."]}


class ShoppingContextTest(unittest.TestCase):
    def setUp(self):
        self.key = ObjectId()
        self.request = "Vou fazer um churrasco para 10 pessoas. Todos são alérgicos a carne de porco."
        self.event = Event(124, "Churrasco de sábado", self.request, datetime(2026, 11, 1, 12), 120,
                           "Casa", 10, recipes=[{"title": "Churrasco bovino", "ingredients": [
                               {"ingredient": "Picanha", "total_quantity": "2 kg"},
                               {"ingredient": "Arroz", "total_quantity": "500 g"}]}], _id=self.key)
        self.history = [{"role": "assistant", "content": "Ovos mexidos", "receita": EGGS}]
        assunto = assunto_do_turno(self.history, self.request, {
            "intencao": "Criar evento", "evento": {"_id": str(self.key), "titulo": self.event.title}}, None)
        self.history += [{"role": "user", "content": self.request},
                         {"role": "assistant", "content": "Churrasco criado. Sugiro picanha e arroz.", "assunto": assunto}]
        self.source = resolver_assunto(self.history, "Monte uma lista de compras")
        self.source["lista_evento"] = True

    def test_lista_generica_prioriza_churrasco_e_preserva_restricao(self):
        context = flow._contexto_receita({"historico": self.history, "mensagem": "Monte uma lista de compras"})
        self.assertIn("Churrasco de sábado", context)
        self.assertIn("alérgicos", context)
        self.assertNotIn("Ovos mexidos", context)

    def test_assunto_evento_sobrevive_ao_salvamento_e_leitura_da_conversa(self):
        doc = {"historico": self.history[:1]}
        collection = Mock()
        collection.find_one.return_value = doc
        def update(query, changes):
            doc["historico"].extend(changes["$push"]["historico"]["$each"])
            return Mock(matched_count=1)
        collection.update_one.side_effect = update
        session = str(ObjectId())
        with patch.object(ConversationsRepository, "conversations_collection", collection):
            ConversationsRepository.append_messages(session, self.request, "Churrasco criado.", assunto=self.history[-1]["assunto"])
            history = ConversationsRepository.get_historico(session)
        context = flow._contexto_receita({"historico": history, "mensagem": "Monte uma lista de compras"})
        self.assertIn("Churrasco de sábado", context)
        self.assertNotIn("Ovos mexidos", context)

    def test_sessao_antiga_sem_metadado_tambem_nao_volta_aos_ovos(self):
        self.history[-1].pop("assunto")
        source = resolver_assunto(self.history, "Monte uma lista de compras")
        self.assertEqual(source["tipo"], "evento")
        self.assertIn("porco", source["pedido"])

    def test_referencia_explicita_pode_voltar_aos_ovos(self):
        source = resolver_assunto(self.history, "Faça a lista dos Ovos mexidos")
        self.assertEqual(source["tipo"], "receita")
        self.assertEqual(source["receita"], EGGS)

    def test_nova_receita_avulsa_muda_assunto(self):
        source = assunto_do_turno(self.history, "Quero ovos mexidos", {"intencao": "Recomendar receita"}, EGGS)
        self.assertEqual(source["tipo"], "receita")

    def test_alterar_evento_nao_apaga_restricoes_anteriores(self):
        source = assunto_do_turno(self.history, "Adie o evento para domingo", {"intencao": "Adiar evento"}, None)
        self.assertIn(self.request, source["restricoes_declaradas"])

    def test_novo_evento_nao_herda_restricoes_dos_convidados_do_anterior(self):
        source = assunto_do_turno(self.history, "Crie outro evento, aniversário", {
            "intencao": "Criar evento", "evento": {"_id": str(ObjectId()), "titulo": "Aniversário"}}, None)
        self.assertNotIn("restricoes_declaradas", source)
        self.assertNotIn("porco", source["pedido"])

    def test_generico_nao_se_confunde_com_itens_ou_receita_explicitos(self):
        for text in ("Monte uma lista de compras", "Pode montar a lista de compras?", "Agora crie a lista", "Sim, monte a lista"):
            with self.subTest(text=text):
                self.assertTrue(pedido_lista_generico(text))
        for text in ("Lista dos ovos mexidos", "Crie uma lista com duas maçãs", "Crie lista chamada Viagem"):
            with self.subTest(text=text):
                self.assertFalse(pedido_lista_generico(text))

    def test_receita_avulsa_nao_pode_ser_persistida_no_lugar_do_evento(self):
        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(ShoppingListsRepository, "create_list") as save:
            result = mongodb_tools.create_list.invoke({"title": "Ovos mexidos", "items": [
                {"name": "Ovos", "quantity": 2, "unitOfMeasure": "unidades"}]})
        self.assertIn("evento ativo", result)
        save.assert_not_called()

    def test_lista_persistida_usa_cardapio_do_evento_mesmo_com_ingredientes_errados_do_modelo(self):
        captured = []
        def save(shopping):
            shopping.id = ObjectId()
            captured.append(shopping.to_dict())
            return shopping

        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(mongodb_tools.events_repository, "get_event_by_id", return_value=self.event), \
             patch.object(recipe_tools, "get_stock") as stock, \
             patch.object(ShoppingListsRepository, "create_list", side_effect=save):
            stock.invoke.return_value = "O usuário não possui nenhum produto cadastrado no estoque."
            result = mongodb_tools.create_list.invoke({"event_id": str(self.key), "title": "Ovos mexidos",
                "items": [{"name": "Ovos", "quantity": 2, "unitOfMeasure": "unidades"}]})
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["title"], self.event.title)
        self.assertEqual(captured[0]["event_id"], str(self.key))
        self.assertEqual([i["name"] for i in captured[0]["array_list"]], ["Picanha", "Arroz"])
        self.assertEqual([i["quantity"] for i in captured[0]["array_list"]], [2, 500])
        self.assertEqual(json.loads(result)["title"], self.event.title)

    def test_outro_evento_nao_pode_substituir_o_ativo(self):
        self.event.id = ObjectId()
        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(mongodb_tools.events_repository, "get_event_by_id", return_value=self.event), \
             patch.object(ShoppingListsRepository, "create_list") as save:
            result = mongodb_tools.create_list.invoke({"event_id": str(self.event.id), "title": "Outro", "items": []})
        self.assertIn("não corresponde", result)
        save.assert_not_called()

    def test_evento_sem_cardapio_pede_confirmacao_e_nao_usa_receita_antiga(self):
        self.event.recipes = []
        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(mongodb_tools.events_repository, "get_event_by_id", return_value=self.event), \
             patch.object(ShoppingListsRepository, "create_list") as save:
            result = mongodb_tools.create_list.invoke({"event_id": str(self.key), "title": "Ovos", "items": []})
        self.assertIn("confirmação dos pratos", result)
        save.assert_not_called()

    def test_falha_de_estoque_impede_gravacao_sem_trocar_origem(self):
        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(mongodb_tools.events_repository, "get_event_by_id", return_value=self.event), \
             patch.object(recipe_tools, "get_stock") as stock, \
             patch.object(ShoppingListsRepository, "create_list") as save:
            stock.invoke.return_value = "FALHA: indisponível"
            result = mongodb_tools.create_list.invoke({"event_id": str(self.key), "title": "Churrasco", "items": []})
        self.assertIn("FALHA", result)
        save.assert_not_called()

    def test_contexto_nao_vaza_para_outra_requisicao(self):
        with identidade.da_requisicao(124, 124, assunto=self.source):
            with identidade.da_requisicao(125, 125):
                self.assertIsNone(identidade.assunto())
            self.assertEqual(identidade.assunto()["tipo"], "evento")
        self.assertIsNone(identidade.assunto())

    def test_recomendacao_recebe_alergia_dos_convidados(self):
        from app.core import agents
        agent = Mock()
        agent.invoke.return_value = {"messages": [AIMessage(content='{"receita":{"titulo":"Churrasco bovino"}}')]}
        with identidade.da_requisicao(124, 124, assunto=self.source), \
             patch.object(flow, "_restricoes_prontas", return_value="nenhuma restrição registrada"), \
             patch.dict(agents.AGENTES_DAS_SKILLS, {"receita-para-evento": agent}):
            general_tools.recomendar_receita.invoke({"description": "Churrasco para 10 pessoas"})
        sent = agent.invoke.call_args.args[0]["messages"][0]["content"]
        self.assertIn("alérgicos", sent)
        self.assertIn("porco", sent)
