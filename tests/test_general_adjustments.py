"""Regressões dos problemas observados pela API, sem rede ou dados reais."""

import json
import unittest
from datetime import date
from unittest.mock import patch

from bson import ObjectId

from app.auth import identidade
from app.guardrails import guardrails
from app.model.mongodb.recipe import Recipe
from app.model.mongodb.shopping_list import ShoppingList
from app.repository.mongodb.shopping_lists import ShoppingListsRepository
from app.schemas import flow
from app.tools import mongo_recipe_tools, mongodb_tools, recipe_tools
from app.validation import ingredientes_basicos_ausentes


class PrivacyRegressionTest(unittest.TestCase):
    def test_titulo_numerico_nao_e_telefone(self):
        for title in ("Teste Ceris 202610250121 acf7 arroz", "Compras 20261025", "Evento 01/11/2026 12:00"):
            with self.subTest(title=title):
                self.assertEqual(guardrails.anonimizar(title), (title, {}))
                self.assertEqual(guardrails.checar_saida(title, {}, revisar=False)["conteudo"], title)

    def test_telefone_real_continua_mascarado(self):
        for number in ("11987654321", "(11) 98765-4321", "11 98765 4321", "11 3456-7890",
                       "+55 (11) 98765-4321", "5511987654321"):
            text, mapping = guardrails.anonimizar("ligue para " + number)
            self.assertNotIn(number, text)
            self.assertEqual(len(mapping), 1)

    def test_token_antigo_nao_vaza_sem_mapa_da_requisicao(self):
        result = guardrails.checar_saida("Lista [PII_TELEFONE_abc123]", {}, revisar=False)
        self.assertEqual(result["conteudo"], "Lista [TELEFONE OMITIDO]")

    def test_lista_nao_persiste_marcador_no_titulo(self):
        for title in ("Lista [PII_TELEFONE_abc123]", "Lista [TELEFONE OMITIDO]"):
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    ShoppingList(124, title, [])


class RecipeRegressionTest(unittest.TestCase):
    def test_tempo_compativel_com_core_e_legados(self):
        recipe = Recipe("Arroz", 2, [], "Cozinhe.", 124, preparation_time_minutes=25)
        self.assertEqual(recipe.to_dict()["estimated_time"], "25 minutos")
        doc = recipe.to_dict()
        doc.pop("preparation_time_minutes")
        self.assertEqual(Recipe.from_dict(doc).preparation_time_minutes, 25)
        doc["estimated_time"] = "1 hora"
        legacy = Recipe.from_dict(doc)
        self.assertIsNone(legacy.preparation_time_minutes)
        self.assertEqual(legacy.to_dict()["estimated_time"], "1 hora")

    def test_consulta_usa_preparo_persistido_e_nao_versao_reescrita(self):
        stored = {"title": "Arroz", "serving_size": 2,
                  "ingredients": [{"name": "Arroz", "required_quantity": "150 g"}],
                  "instructions": "Cozinhe com a panela semitampada.", "preparation_time_minutes": 15}
        response = json.dumps({"intencao": "Buscar receita anterior", "resposta": "Não encontrei.",
                               "receita": {"title": "Outra", "instructions": "Sem tampar."}})
        aligned = flow._alinhar_receita_consultada(response, [
            {"ferramenta": "buscar_receitas_usuario", "conteudo": json.dumps([stored])}])
        result = flow._montar_sem_modelo(aligned)
        self.assertIn("panela semitampada", result)
        self.assertNotIn("Sem tampar", result)
        self.assertNotIn("Não encontrei", result)

    def test_consulta_ambigua_nao_escolhe_uma_receita(self):
        response = json.dumps({"intencao": "Buscar receita anterior", "esclarecer": "Qual arroz?"})
        self.assertEqual(flow._alinhar_receita_consultada(response, [
            {"ferramenta": "buscar_receitas_usuario", "conteudo": '[{"title":"A"},{"title":"B"}]'}]), response)

    def test_omissao_de_sal_e_agua_nao_vira_receita_completa(self):
        recipe = {"titulo": "Arroz", "ingredientes": [{"ingrediente": "Arroz", "quantidade_total": "150 g"}],
                  "instrucoes": ["Acrescente água fervente e sal."]}
        result = flow._montar_sem_modelo(json.dumps({"resposta": "Receita pronta", "receita": recipe}))
        self.assertIn("incompleta", result)
        self.assertIn("água", result)
        self.assertIn("sal", result)

    def test_agua_para_lavar_nao_exige_ingrediente(self):
        self.assertEqual(ingredientes_basicos_ausentes([], "Lave os tomates com água."), [])

    def test_restricao_citada_no_preparo_nao_e_ingrediente_usado(self):
        self.assertEqual(ingredientes_basicos_ausentes([], "Cozinhe sem sal. Não use leite."), [])

    def test_receita_estruturada_sobrevive_a_troca_de_secoes(self):
        recipe = {"titulo": "Arroz", "ingredientes": [{"ingrediente": "Arroz", "quantidade_total": "150 g"}],
                  "instrucoes": ["Cozinhe com a panela semitampada."]}
        history = [{"role": "assistant", "content": "Receita", "receita": recipe}]
        history += [{"role": "user", "content": "Eventos e listas"}] * 20
        self.assertFalse(any("receita" in t for t in flow._ultimos_turnos(history, 10)))
        recovered = flow._ultima_receita(history)
        self.assertEqual(recovered, recipe)
        recovered["instrucoes"][0] = "Alterado"
        self.assertEqual(recipe["instrucoes"][0], "Cozinhe com a panela semitampada.")
        self.assertIn("panela semitampada", flow._contexto_receita({"historico": history}))

    def test_omissao_de_ingredientes_impede_salvamento(self):
        with identidade.da_requisicao(124, 124), patch.object(mongo_recipe_tools.RecipesRepository, "create_recipe") as save:
            result = mongo_recipe_tools.salvar_receita.invoke({
                "titulo": "Arroz", "serving_size": 2, "ingredientes": [{"nome": "Arroz", "quantidade": "150 g"}],
                "instrucoes": "Acrescente água e sal.", "tempo_preparo_minutos": 15, "dificuldade": "fácil"})
        self.assertIn("FALHA", result)
        save.assert_not_called()


class StockRegressionTest(unittest.TestCase):
    def test_estoque_vazio_e_zero_confirmado_sem_conversao_de_medidas(self):
        result = recipe_tools.calculate_missing([{"name": "Arroz", "quantity": "2 xícaras"}], [], date(2026, 10, 25))
        check = result["conferencia"][0]
        self.assertTrue(check["comparacao_confirmada"])
        self.assertEqual(check["quantidade_disponivel"], 0)
        self.assertEqual(result["itens_para_comprar"][0]["quantity"], 2)

    def test_resposta_inesperada_nao_vira_estoque_vazio(self):
        with patch.object(recipe_tools, "get_stock") as stock:
            stock.invoke.return_value = "consulta inesperada"
            result = recipe_tools.ingredientes_para_comprar.invoke({"ingredientes": [{"name": "Arroz", "quantity": "150 g"}]})
        self.assertTrue(result.startswith("FALHA"))

    def test_revisao_vazia_nao_oferece_adicionar(self):
        state = {"trace_id": "test", "rota": "estoque", "mapa_pii": {},
                 "resposta_agente": json.dumps({"intencao": "Revisar estoque"}),
                 "resposta_final": "Seu estoque está vazio. Gostaria de adicionar algo?",
                 "evidencias": [{"ferramenta": "get_stock", "conteudo": "[]"}]}
        with patch.object(flow, "checar_saida", return_value={"conteudo": state["resposta_final"]}):
            result = flow.guardrail_saida(state)
        self.assertNotIn("adicionar", result["resposta_final"])


class ItemRegressionTest(unittest.TestCase):
    def setUp(self):
        context = identidade.da_requisicao(124, 124)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.saved = ShoppingList(124, "Compras", [
            {"id": "maca", "name": "Maçã", "quantity": 2, "unitOfMeasure": "unidade", "checked": False},
            {"id": "leite", "name": "Leite", "quantity": 1, "unitOfMeasure": "litro", "checked": False}], _id=ObjectId())

    def test_alterar_leite_nao_marca_maca(self):
        with patch.object(ShoppingListsRepository, "get_list", return_value=self.saved), \
             patch.object(ShoppingListsRepository, "update_list", return_value=self.saved) as save:
            mongodb_tools.alterar_item_lista.invoke({"list_id": str(self.saved.id), "item_id": "leite",
                                                   "operacao": "quantidade", "quantidade": 2})
        items = save.call_args.kwargs["items"]
        self.assertEqual(items[0], self.saved.items[0])
        self.assertEqual(items[1]["quantity"], 2)
        self.assertFalse(items[1]["checked"])

    def test_quantidade_nao_aceita_alteracao_de_comprado(self):
        with patch.object(ShoppingListsRepository, "get_list", return_value=self.saved), \
             patch.object(ShoppingListsRepository, "update_list") as save:
            result = mongodb_tools.alterar_item_lista.invoke({"list_id": str(self.saved.id), "item_id": "leite",
                                                            "operacao": "quantidade", "quantidade": 2, "comprado": True})
        self.assertIn("FALHA", result)
        save.assert_not_called()

    def test_item_de_outra_lista_nao_e_alterado(self):
        with patch.object(ShoppingListsRepository, "get_list", return_value=self.saved), \
             patch.object(ShoppingListsRepository, "update_list") as save:
            result = mongodb_tools.alterar_item_lista.invoke({"list_id": str(self.saved.id), "item_id": "outro",
                                                            "operacao": "comprado", "comprado": True})
        self.assertIn("FALHA", result)
        save.assert_not_called()

    def test_ids_legados_estaveis_e_identidade_do_core_preservada(self):
        doc = self.saved.to_dict()
        doc["array_list"][0].pop("id")
        doc["array_list"][1]["_id"] = doc["array_list"][1].pop("id")
        first, second = ShoppingList.from_dict(doc), ShoppingList.from_dict(doc)
        self.assertEqual(first.items, second.items)
        self.assertEqual(first.items[1]["id"], "leite")

    def test_skill_nao_expoe_substituicao_integral_dos_itens(self):
        from app.core.skills import SKILLS
        tools = SKILLS["lista-gerenciar"].ferramentas
        self.assertNotIn("update_list", tools)
        self.assertIn("alterar_item_lista", tools)

    def test_nova_ferramenta_conta_como_gravacao_confirmada(self):
        data = self.saved.to_dict()
        evidence = [{"ferramenta": "alterar_item_lista", "conteudo": json.dumps(data, default=str)}]
        response = json.dumps({"intencao": "Atualizar lista de compras", "lista": {"_id": str(self.saved.id)}})
        with patch.object(flow, "_invocar_agente", return_value=(response, 0, 0, evidence)) as invoke:
            result, *_ = flow._invocar_com_confirmacao(object(), "Altere leite.", [], "teste")
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(json.loads(result)["lista"]["title"], "Compras")
        self.assertIsNotNone(flow._lista_gravada(result, evidence))

    def test_consulta_preserva_titulo_quantidade_e_compra(self):
        response = json.dumps({"intencao": "Consultar lista de compras", "resposta": "Lista Teste: 3 maçãs compradas"})
        evidence = [{"ferramenta": "get_list", "conteudo": json.dumps([self.saved.to_dict()], default=str)}]
        aligned = flow._alinhar_lista_consultada(response, evidence)
        self.assertEqual(json.loads(aligned)["lista"]["title"], "Compras")
        self.assertFalse(json.loads(aligned)["lista"]["array_list"][0]["checked"])

    def test_listas_iguais_tem_opcoes_numeradas(self):
        lists = [{"title": "Nova lista 1", "array_list": []}] * 2
        response = json.dumps({"intencao": "Consultar lista de compras", "resposta": "Qual lista?"})
        aligned = flow._alinhar_lista_consultada(response, [{"ferramenta": "get_list", "conteudo": json.dumps(lists)}])
        result = flow._montar_sem_modelo(aligned)
        self.assertIn("1) Nova lista 1", result)
        self.assertIn("2) Nova lista 1", result)
