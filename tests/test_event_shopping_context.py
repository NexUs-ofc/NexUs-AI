"""Receita avulsa → evento com restrição → lista genérica, sem bancos reais."""

import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from bson import ObjectId
from langchain_core.messages import AIMessage

from app.auth import identidade
from app.core.contexto_conversa import (
    assunto_do_turno,
    pedido_evento_composto,
    pedido_lista_generico,
    resolver_assunto,
)
from app.model.mongodb.event import Event
from app.repository.mongodb.conversations import ConversationsRepository
from app.repository.mongodb.shopping_lists import ShoppingListsRepository
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

    def test_pedido_composto_com_prepare_do_evento_e_reconhecido(self):
        self.assertTrue(pedido_evento_composto(
            "Monte uma lista de compras e prepare o evento, salve essa receita também por favor"
        ))

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
            ConversationsRepository.append_messages(session, self.request, "Churrasco criado.", account_id=124, assunto=self.history[-1]["assunto"])
            history = ConversationsRepository.get_historico(session, 124)
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

    def test_confirmacao_curta_preserva_receita_pendente(self):
        pending = {"tipo": "receita_pendente", "pedido":
                   "Faça uma receita de arroz para duas pessoas, sem óleo"}
        history = [{"role": "assistant", "content": "Posso completar a receita?",
                    "assunto": pending}]
        for answer in ("sim", "pode", "não", "2 porções"):
            with self.subTest(answer=answer):
                self.assertEqual(resolver_assunto(history, answer), pending)

    def test_pedido_novo_nao_herda_receita_pendente(self):
        pending = {"tipo": "receita_pendente", "pedido": "Faça uma receita de arroz"}
        history = [{"role": "assistant", "content": "Posso completar?", "assunto": pending}]
        self.assertIsNone(resolver_assunto(history, "Qual a previsão do tempo?"))

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
        self.assertEqual(captured[0]["date"], "2026-11-01")
        self.assertEqual([i["name"] for i in captured[0]["array_list"]], ["Picanha", "Arroz"])
        self.assertEqual(json.loads(result)["date"], "2026-11-01")
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

    def test_pedido_composto_da_prioridade_ao_fluxo_de_eventos(self):
        request = (
            "Bom, amanha farei um evento para 6 pessoas, quero esse prato, gostaria de ter "
            "essa receita salva, uma lista de compras com ingredientes que eu compraria, "
            "e o evento marcado na minha casa para as 14h"
        )
        self.assertTrue(pedido_evento_composto(request))
        self.assertTrue(pedido_lista_generico(request))
        self.assertEqual(flow.decidir_rota({"mensagem": request, "rota": "receitas", "historico": []}), "eventos")
        self.assertEqual(flow._escolher_skill("eventos", {"mensagem": request, "historico": []}),
                         "evento-criar-completo")

    def test_pergunta_duracao_antes_de_qualquer_escrita(self):
        request = (
            "Amanha farei um evento para 6 pessoas, quero esse prato, gostaria de ter "
            "essa receita salva, uma lista de compras com ingredientes que eu compraria, "
            "e o evento marcado na minha casa para as 14h"
        )
        state = {"trace_id": "trace-test", "historico": [], "mensagem": request,
                 "evidencias": [], "input_tokens": 0, "output_tokens": 0}
        with patch.object(flow, "span"), patch.object(flow, "_invocar_com_confirmacao") as invoke:
            result = flow.agente_eventos(state)
        self.assertIn("duração", result["resposta_final"])
        invoke.assert_not_called()

    def test_resposta_de_duracao_mantem_pedido_composto_pendente(self):
        pending = {"tipo": "evento", "pedido": "Crie evento, salve a receita e monte lista de compras",
                   "evento_pendente_criacao": True}
        history = [{"role": "assistant", "content": "Qual a duração?", "assunto": pending}]
        self.assertEqual(resolver_assunto(history, "2 horas"), pending)

    def test_resposta_de_duracao_nao_confunde_horario_com_duracao(self):
        request = "Amanha farei evento e marque para as 14h"
        state = {"trace_id": "trace-test", "historico": [], "mensagem": request,
                 "evidencias": [], "input_tokens": 0, "output_tokens": 0}
        with patch.object(flow, "span"), patch.object(flow, "_invocar_com_confirmacao") as invoke:
            result = flow.agente_eventos(state)
        self.assertIn("duração", result["resposta_final"])
        invoke.assert_not_called()

    def test_pedido_composto_passa_primeiro_pelo_agente_de_receitas_e_depois_eventos(self):
        recipe = {
            "title": "Frango ao molho", "serving_size": 4,
            "ingredients": [{"name": "Frango", "required_quantity": "500 g"}],
            "instructions": "Tempere e cozinhe o frango.",
            "preparation_time_minutes": 40, "difficulty": "fácil",
        }
        request = (
            "Amanhã farei um evento para 6 pessoas. Quero esse prato e essa receita salva, uma lista de compras "
            "com ingredientes que eu compraria e o evento na minha casa às 14h, por 3 horas."
        )
        saved_recipe = {**recipe, "_id": "recipe-1"}
        saved_list = {"_id": "list-1", "title": "Evento", "array_list": [
            {"name": "Arroz", "quantity": 1, "unitOfMeasure": "kg", "checked": False}
        ]}
        recipe_evidence = [{"ferramenta": "salvar_receita", "conteudo": json.dumps({
            "status": "sucesso", "receita": saved_recipe,
        })}]
        event_evidence = [
            {"ferramenta": "create_event", "conteudo": "Evento criado"},
            {"ferramenta": "create_list", "conteudo": json.dumps(saved_list)},
        ]
        event_response = json.dumps({
            "dominio": "events", "intencao": "Criar lista de compras",
            "resposta": "Concluído", "lista": saved_list,
        })
        state = {"trace_id": "trace-test", "historico": [
            {"role": "assistant", "content": "Frango ao molho", "receita": recipe},
        ], "mensagem": request, "evidencias": [], "input_tokens": 0, "output_tokens": 0}
        with patch.object(flow, "span"), patch.object(
            flow, "_invocar_com_confirmacao",
            side_effect=[
                (json.dumps({"intencao": "Salvar receita", "resposta": "Salva."}), 1, 1, recipe_evidence),
                (event_response, 2, 2, event_evidence),
            ],
        ) as invoke:
            result = flow.agente_eventos(state)

        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(invoke.call_args_list[0].args[0], flow.AGENTES_DAS_SKILLS["receita-anterior"])
        self.assertEqual(invoke.call_args_list[1].args[0], flow.AGENTES_DAS_SKILLS["evento-criar-completo"])
        self.assertIn("RECEITA_SALVA_E_CONFIRMADA_PELO_AGENTE_DE_RECEITAS", invoke.call_args_list[1].args[1])
        self.assertIn("Criei o evento", result["resposta_final"])
        self.assertIn("Salvei a receita Frango ao molho", result["resposta_final"])
