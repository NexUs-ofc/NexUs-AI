import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from bson import ObjectId

from app.auth import identidade
from app.model.mongodb.recipe import Recipe
from app.model.mongodb.shopping_list import ShoppingList
from app.repository.mongodb.recipes import RecipesRepository
from app.repository.mongodb.shopping_lists import ShoppingListsRepository
from app.tools import mongo_recipe_tools, mongodb_tools


class RecipeStorageTest(unittest.TestCase):
    def setUp(self):
        context = identidade.da_requisicao(124, 124)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.args = {
            "titulo": "Arroz de panela", "serving_size": 2,
            "ingredientes": [{"ingrediente": "Arroz", "quantidade_total": "200 g"}],
            "instrucoes": "1. Lave o arroz.\n2. Cozinhe por 20 minutos.",
            "tempo_preparo_minutos": 25, "dificuldade": "fácil",
        }

    def test_salvar_preserva_quantidades_tempo_dificuldade_e_data(self):
        captured = []
        def save(recipe):
            captured.append(recipe.to_dict())
            recipe.id = ObjectId()
            return recipe
        with patch.object(RecipesRepository, "create_recipe", side_effect=save):
            response = mongo_recipe_tools.salvar_receita.invoke(self.args)
        self.assertIn("sucesso", response)
        doc = captured[0]
        self.assertEqual(doc["ingredients"][0]["required_quantity"], "200 g")
        self.assertEqual(doc["ingredients"][0]["name"], "Arroz")
        self.assertEqual(doc["preparation_time_minutes"], 25)
        self.assertEqual(doc["difficulty"], "easy")
        self.assertEqual(doc["account_id"], 124)
        self.assertIsInstance(doc["created_at"], datetime)

    def test_receita_incompleta_nao_e_salva(self):
        for field, value in (("instrucoes", " "), ("titulo", ""), ("serving_size", 0),
                             ("ingredientes", [{"nome": "Arroz"}])):
            with self.subTest(field=field):
                args = {**self.args, field: value}
                with patch.object(RecipesRepository, "create_recipe") as save:
                    try:
                        response = mongo_recipe_tools.salvar_receita.invoke(args)
                    except ValueError:
                        pass
                    else:
                        self.assertIn("FALHA", response)
                    save.assert_not_called()

    def test_busca_de_salvas_devolve_receita_inteira_com_id(self):
        recipe = Recipe(
            title="Arroz", serving_size=2, account_id=124,
            ingredients=[{"name": "Arroz", "required_quantity": "200 g"}],
            instructions="Cozinhe por 20 minutos.", _id=ObjectId(),
        )
        with patch.object(RecipesRepository, "get_user_recipes", return_value=[recipe]):
            response = mongo_recipe_tools.buscar_receitas_usuario.invoke({})
        self.assertIn("Cozinhe por 20 minutos.", response)
        self.assertIn(str(recipe.id), response)

    def test_erro_de_consulta_nao_vira_nenhuma_receita(self):
        from pymongo.errors import ConnectionFailure
        collection = Mock()
        collection.find.side_effect = ConnectionFailure("sem conexão")
        with patch.object(RecipesRepository, "recipes_collection", collection):
            try:
                RecipesRepository.get_user_recipes(124)
            except RuntimeError:
                pass
            else:
                self.fail("falha do banco foi tratada como lista vazia")


class ShoppingContractTest(unittest.TestCase):
    def test_colecao_e_formato_compativeis_com_o_core(self):
        self.assertEqual(ShoppingListsRepository.shopping_lists_collection.name, "shopping_list")
        shopping = ShoppingList(
            household_id=124, title="Jantar",
            items=[{"ingredient": "Arroz", "quantity": "200 g", "purchased": False}],
        )
        doc = shopping.to_dict()
        self.assertIn("array_list", doc)
        self.assertNotIn("items", doc)
        item = doc["array_list"][0]
        self.assertEqual(item["name"], "Arroz")
        self.assertEqual(item["quantity"], 200)
        self.assertEqual(item["unitOfMeasure"], "g")
        self.assertFalse(item["checked"])
        self.assertTrue(item["id"])

    def test_leitura_do_documento_do_core_preserva_ids_e_compra(self):
        doc = {
            "_id": ObjectId(), "household_id": 124, "title": "Jantar", "event_id": None,
            "array_list": [{"id": "item-core", "foodId": None, "name": "Arroz",
                            "quantity": 200.0, "unitOfMeasure": "g", "checked": True}],
        }
        shopping = ShoppingList.from_dict(doc)
        self.assertEqual(shopping.to_dict()["array_list"], doc["array_list"])

    def test_modelo_pode_localizar_lista_pelo_titulo(self):
        self.assertIn("title", mongodb_tools.get_list.args)
        self.assertNotIn("list_id", mongodb_tools.get_list.args_schema.model_json_schema().get("required", []))

    def test_consulta_por_id_filtra_dono(self):
        collection = Mock()
        collection.find_one.return_value = None
        key = ObjectId()
        with patch.object(ShoppingListsRepository, "shopping_lists_collection", collection):
            ShoppingListsRepository.get_list(str(key), household_id=124)
        self.assertEqual(collection.find_one.call_args.args[0], {"_id": key, "household_id": 124})

    def test_repeticao_da_criacao_na_mesma_requisicao_nao_duplica(self):
        args = {"event_id": "", "title": "Jantar",
                "items": [{"ingredient": "Arroz", "quantity": "200 g", "purchased": False}]}
        saved = ShoppingList(household_id=124, title="Jantar", items=args["items"], _id=ObjectId())
        with patch.object(ShoppingListsRepository, "create_list", return_value=saved) as create:
            with identidade.da_requisicao(124, 124):
                mongodb_tools.create_list.invoke(args)
                mongodb_tools.create_list.invoke(args)
            self.assertEqual(create.call_count, 1)

    def test_consulta_retorna_json_utilizavel_pelo_agente(self):
        saved = ShoppingList(household_id=124, title="Jantar", items=[], _id=ObjectId())
        with patch.object(ShoppingListsRepository, "get_lists", return_value=[saved]), identidade.da_requisicao(124, 124):
            response = mongodb_tools.get_list.invoke({"title": "Jantar"})
        data = json.loads(response)
        self.assertEqual(data[0]["title"], "Jantar")
        self.assertIn("_id", data[0])

class RecipeFormattingTest(unittest.TestCase):
    def test_receita_salva_em_ingles_aparece_completa_e_sem_numeracao_dupla(self):
        from app.schemas.flow import _formatar_receita
        result = _formatar_receita({
            "title": "Arroz", "serving_size": 2,
            "ingredients": [{"name": "Arroz", "required_quantity": "200 g"}],
            "instructions": "1. Lave.\n2. Cozinhe.",
            "preparation_time_minutes": 25, "difficulty": "easy",
        })
        self.assertIn("Arroz: 200 g", result)
        self.assertIn("2 porções", result)
        self.assertIn("25 minutos", result)
        self.assertIn("fácil", result)
        self.assertIn("1. Lave.\n2. Cozinhe.", result)
        self.assertNotIn("1. 1.", result)

    def test_nao_apresenta_receita_incompleta_como_pronta(self):
        from app.schemas.flow import _montar_sem_modelo
        result = _montar_sem_modelo(json.dumps({
            "resposta": "Aqui está a receita.",
            "receita": {"titulo": "Arroz", "ingredientes": [], "instrucoes": []},
        }))
        self.assertIn("Não consegui recuperar", result)

    def test_lista_mostra_quantidades_reais_e_item_comprado(self):
        from app.schemas.flow import _montar_sem_modelo
        result = _montar_sem_modelo(json.dumps({
            "resposta": "Lista atualizada.",
            "lista": {"title": "Jantar", "array_list": [
                {"name": "Arroz", "quantity": 50.0, "unitOfMeasure": "g", "checked": True},
            ]},
        }))
        self.assertIn("Arroz: 50 g (comprado)", result)

    def test_resultado_do_calculo_corrige_estado_do_estoque_no_envelope(self):
        from app.schemas.flow import _alinhar_receita_estoque
        result = json.loads(_alinhar_receita_estoque(json.dumps({
            "receita": {"ingredientes": [{"ingrediente": "Arroz", "tem_suficiente": True}],
                        "ingredientes_faltantes": ["Água"]},
        }), [{"ferramenta": "ingredientes_para_comprar", "conteudo": json.dumps({
            "conferencia": [{"nome": "Arroz", "tem_suficiente": False, "comparacao_confirmada": True}],
            "itens_para_comprar": [{"name": "Arroz", "quantity": 50}],
        })}]))
        self.assertFalse(result["receita"]["ingredientes"][0]["tem_suficiente"])
        self.assertEqual(result["receita"]["ingredientes_faltantes"], ["Arroz"])


class MissingIngredientsTest(unittest.TestCase):
    def setUp(self):
        from datetime import date
        self.today = date(2026, 10, 25)
        self.stock = [{"food_name": "Arroz", "quantity": 2, "package_quantity": "0.1",
                       "unit_of_measure": "kg", "expiry_date": "2026-11-20"}]

    def calculate(self, ingredients, stock=None):
        from app.tools.recipe_tools import calculate_missing
        return calculate_missing(ingredients, self.stock if stock is None else stock, self.today)

    def test_desconta_pacotes_em_kg_de_necessidade_em_gramas(self):
        result = self.calculate([{"ingredient": "Arroz", "quantity": "350 g"}])
        self.assertEqual(result["itens_para_comprar"][0]["quantity"], 150)
        self.assertEqual(result["conferencia"][0]["quantidade_disponivel"], 200)

    def test_soma_lotes_e_nao_compra_o_que_ja_tem(self):
        result = self.calculate([{"ingredient": "Arroz", "quantity": "350 g"}], self.stock * 2)
        self.assertEqual(result["itens_para_comprar"], [])
        self.assertTrue(result["conferencia"][0]["tem_suficiente"])

    def test_lote_vencido_ou_sem_data_nao_vira_ingrediente_disponivel(self):
        for expiry in ("2026-10-24", None):
            with self.subTest(expiry=expiry):
                result = self.calculate([{"ingredient": "Arroz", "quantity": "350 g"}],
                                        [{**self.stock[0], "expiry_date": expiry}])
                self.assertEqual(result["itens_para_comprar"][0]["quantity"], 350)

    def test_nao_converte_xicara_para_gramas_por_palpite(self):
        result = self.calculate([{"ingredient": "Arroz", "quantity": "2 xícaras"}])
        self.assertFalse(result["conferencia"][0]["comparacao_confirmada"])
        self.assertIsNone(result["conferencia"][0]["quantidade_disponivel"])

    def test_agua_de_preparo_nao_vira_compra_mas_mineral_sim(self):
        result = self.calculate([{"ingredient": "Água", "quantity": "300 ml"},
                                 {"ingredient": "Água mineral", "quantity": "1 l"}])
        self.assertEqual([i["name"] for i in result["itens_para_comprar"]], ["Água mineral"])

    def test_ingrediente_repetido_nao_desconta_estoque_duas_vezes(self):
        result = self.calculate([{"ingredient": "Arroz", "quantity": "150 g"}] * 2)
        self.assertEqual(result["itens_para_comprar"][0]["quantity"], 100)


class ListMutationTest(unittest.TestCase):
    def setUp(self):
        ctx = identidade.da_requisicao(124, 124)
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.key = str(ObjectId())
        self.saved = ShoppingList(household_id=124, title="Jantar", items=[
            {"id": "arroz", "name": "Arroz", "quantity": 200, "unitOfMeasure": "g", "checked": True},
            {"id": "leite", "name": "Leite", "quantity": 1, "unitOfMeasure": "l", "checked": False},
        ], _id=ObjectId(self.key))

    def test_renomear_nao_perde_itens_nem_estado_de_compra(self):
        with (
            patch.object(ShoppingListsRepository, "get_list", return_value=self.saved),
            patch.object(ShoppingListsRepository, "update_list", return_value=self.saved) as update,
        ):
            mongodb_tools.update_list.invoke({"list_id": self.key, "title": "Novo título"})
        self.assertEqual(update.call_args.kwargs["items"], self.saved.items)
        self.assertEqual(update.call_args.kwargs["household_id"], 124)

    def test_marcar_compra_preserva_ids_dos_itens(self):
        items = [{**i, "checked": True} for i in self.saved.items]
        with (
            patch.object(ShoppingListsRepository, "get_list", return_value=self.saved),
            patch.object(ShoppingListsRepository, "update_list", return_value=self.saved) as update,
        ):
            mongodb_tools.update_list.invoke({"list_id": self.key, "items": items})
        self.assertEqual([i["id"] for i in update.call_args.kwargs["items"]], ["arroz", "leite"])

    def test_id_de_outro_item_nao_pode_ser_injetado(self):
        with (
            patch.object(ShoppingListsRepository, "get_list", return_value=self.saved),
            patch.object(ShoppingListsRepository, "update_list") as update,
        ):
            result = mongodb_tools.update_list.invoke({
                "list_id": self.key, "items": [{**self.saved.items[0], "id": "outro"}],
            })
        self.assertIn("FALHA", result)
        update.assert_not_called()

    def test_lista_de_outra_casa_nao_e_atualizada(self):
        with (
            patch.object(ShoppingListsRepository, "get_list", return_value=None),
            patch.object(ShoppingListsRepository, "update_list") as update,
        ):
            result = mongodb_tools.update_list.invoke({"list_id": self.key, "title": "Novo"})
        self.assertIn("FALHA", result)
        update.assert_not_called()

    def test_requisicao_nova_nao_herda_cache_de_gravacoes(self):
        action = Mock(return_value="ok")
        identidade.executar_gravacao("teste", {"title": "Arroz"}, action)
        identidade.executar_gravacao("teste", {"title": "Arroz"}, action)
        with identidade.da_requisicao(124, 124):
            identidade.executar_gravacao("teste", {"title": "Arroz"}, action)
        self.assertEqual(action.call_count, 2)

class ConfirmedMutationTest(unittest.TestCase):
    def test_nao_diz_que_marcou_quando_nao_executou_ferramenta(self):
        from app.schemas import flow
        claimed = json.dumps({"dominio": "events", "intencao": "Atualizar lista de compras",
                              "resposta": "Marquei o arroz como comprado."})
        with patch.object(flow, "_invocar_agente", return_value=(claimed, 10, 5, [])) as invoke:
            response, input_tokens, output_tokens, _ = flow._invocar_com_confirmacao(
                object(), "Marque arroz como comprado.", [], "teste",
            )
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(input_tokens, 20)
        self.assertEqual(output_tokens, 10)
        self.assertIn("Não consegui confirmar", json.loads(response)["resposta"])
        self.assertNotIn("Marquei", response)

    def test_retorno_de_erro_nao_e_evidencia_de_gravacao(self):
        from app.schemas import flow
        claimed = json.dumps({"intencao": "Salvar receita", "resposta": "Salvei."})
        with patch.object(flow, "_invocar_agente", return_value=(
            claimed, 0, 0, [{"ferramenta": "salvar_receita", "conteudo": "FALHA: banco indisponível"}],
        )):
            response, *_ = flow._invocar_com_confirmacao(object(), "Salve.", [], "teste")
        self.assertIn("Não consegui confirmar", json.loads(response)["resposta"])

    def test_lista_exibida_reflete_retorno_real_da_atualizacao(self):
        from app.schemas import flow
        claimed = json.dumps({
            "intencao": "Atualizar lista de compras", "resposta": "Atualizei.",
            "lista": {"title": "Inventada", "array_list": []},
        })
        real = {"_id": str(ObjectId()), "title": "Jantar", "array_list": [
            {"id": "arroz", "name": "Arroz", "quantity": 50, "unitOfMeasure": "g", "checked": True},
        ]}
        with patch.object(flow, "_invocar_agente", return_value=(
            claimed, 0, 0, [{"ferramenta": "update_list", "conteudo": json.dumps(real)}],
        )) as invoke:
            response, *_ = flow._invocar_com_confirmacao(object(), "Atualize.", [], "teste")
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(json.loads(response)["lista"], real)

    def test_receita_duplicada_no_texto_do_modelo_e_exibida_uma_vez(self):
        from app.schemas.flow import _montar_sem_modelo
        result = _montar_sem_modelo(json.dumps({
            "resposta": "Ingredientes: Arroz. Modo de preparo: Cozinhe.",
            "receita": {"titulo": "Arroz", "ingredientes": [
                {"ingrediente": "Arroz", "quantidade_total": "200 g"}],
                "instrucoes": ["Cozinhe."]},
        }))
        self.assertEqual(result.count("Ingredientes:"), 1)
        self.assertEqual(result.count("Modo de preparo:"), 1)

    def test_necessidades_com_unidades_diferentes_nao_descontam_duas_vezes(self):
        from datetime import date

        from app.tools.recipe_tools import calculate_missing
        result = calculate_missing(
            [{"ingredient": "Arroz", "quantity": "150 g"},
             {"ingredient": "Arroz", "quantity": "0,15 kg"}],
            [{"food_name": "Arroz", "quantity": 1, "package_quantity": 200,
              "unit_of_measure": "g", "expiry_date": "2026-11-20"}],
            date(2026, 10, 25),
        )
        self.assertEqual(result["itens_para_comprar"][0]["quantity"], 100)



class EquivalentCreationTest(unittest.TestCase):
    def test_aliases_equivalentes_na_revisao_nao_criam_outra_lista(self):
        saved = ShoppingList(household_id=124, title="Jantar", items=[], _id=ObjectId())
        with (
            identidade.da_requisicao(124, 124),
            patch.object(ShoppingListsRepository, "create_list", return_value=saved) as create,
        ):
            mongodb_tools.create_list.invoke({
                "title": "Jantar",
                "items": [{"ingredient": "Arroz", "quantity": "200 g", "purchased": False}],
            })
            mongodb_tools.create_list.invoke({
                "title": "jantar",
                "items": [{"name": "arroz", "quantity": 200.0, "unitOfMeasure": "g", "checked": False}],
            })
        self.assertEqual(create.call_count, 1)

class TrustedListRenderingTest(unittest.TestCase):
    def test_so_pula_juiz_com_lista_confirmada_no_estado(self):
        from app.schemas.flow import decidir_pos_eventos
        from app.schemas.state import State
        self.assertIn("lista_confirmada", State.__annotations__)
        self.assertEqual(decidir_pos_eventos({"lista_confirmada": True}), "guardrail_saida")
        self.assertEqual(decidir_pos_eventos({}), "juiz")

    def test_json_do_modelo_sem_retorno_de_gravacao_nao_e_confiavel(self):
        from app.schemas.flow import _lista_gravada
        response = json.dumps({"lista": {"_id": str(ObjectId()), "array_list": []}})
        self.assertIsNone(_lista_gravada(response, []))

    def test_confirmacao_precisa_do_id_real_da_lista(self):
        from app.schemas.flow import _lista_gravada
        key = str(ObjectId())
        response = json.dumps({"lista": {"_id": key, "array_list": []}})
        evidence = [{"ferramenta": "create_list",
                     "conteudo": json.dumps({"_id": str(ObjectId()), "array_list": []})}]
        self.assertIsNone(_lista_gravada(response, evidence))
