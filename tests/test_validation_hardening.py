"""Pre-write validation and privacy policy regressions, with synthetic data."""
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from bson import ObjectId
from pydantic import ValidationError

from app.auth import identidade
from app.core import judge
from app.model.mongodb.event import Event
from app.model.mongodb.recipe import Recipe
from app.repository.mongodb.events import EventsRepository
from app.repository.mongodb.recipes import RecipesRepository
from app.schemas import flow
from app.tools import mongo_recipe_tools, mongodb_tools
from app.validation import validar_quantidade_receita

EVENT = {"titulo": "Jantar", "descricao": "Jantar em familia", "data": "2026-11-20T18:00",
         "duracao": 60, "local": "Casa", "qtd_pessoas": 3}
RECIPE = {"titulo": "Arroz", "serving_size": 2,
          "ingredientes": [{"nome": "Arroz", "quantidade": "200 g"}],
          "instrucoes": "Cozinhe o arroz.", "tempo_preparo_minutos": 20, "dificuldade": "facil"}
INVALID_QUANTITIES = ["0 g", "-5 kg", "NaN", "Infinity", "banana", {"value": 0}, [],
                      True, False, None, float("nan"), float("inf"), -1, 0,
                      "1/0 g", "0/2 g", "1e309 g", "2 bananasxyz", "1 g extra",
                      "1/2/3 g", "1 -1/2 g", "1/-2 g"]
VALID_QUANTITIES = ["200 g", "1,5 kg", "0.5 l", "1/2 xicara", "1 1/2 xicaras",
                    "2 colheres de sopa", "1 colher de cha", "1 xicara (cha)",
                    "1 pitada", "2 unidades", "a gosto", "quanto baste",
                    "2 folhas", "1 dente", "1 lata", "250ml", "1/2 colher (sopa)"]


class ValidationHardeningTest(unittest.TestCase):
    def test_invalid_events_never_reach_write_boundary(self):
        cases = [("data", ""), ("data", "invalid"), ("duracao", 0), ("duracao", -10),
                 ("qtd_pessoas", 0), ("qtd_pessoas", -3), ("local", ""),
                 ("descricao", ""), ("duracao", True), ("qtd_pessoas", False),
                 ("duracao", 1.5), ("qtd_pessoas", float("nan"))]
        for key, value in cases:
            with self.subTest(field=key, value=value), identidade.da_requisicao(124, 124), \
                 patch.object(identidade, "executar_gravacao") as write:
                try:
                    result = mongodb_tools.create_event.invoke({**EVENT, key: value})
                    self.assertTrue(str(result).startswith("FALHA:"))
                except ValidationError:
                    pass
                write.assert_not_called()

    def test_valid_event_is_saved_once_with_owner_and_positive_values(self):
        def save(event):
            event.id = ObjectId()
            return event
        with identidade.da_requisicao(124, 124), \
             patch.object(EventsRepository, "create_event", side_effect=save) as write:
            for _ in range(2):
                result = mongodb_tools.create_event.invoke(EVENT)
        self.assertIsInstance(result, Event)
        self.assertEqual(result.household_id, 124)
        self.assertEqual(result.duration, 60)
        self.assertEqual(result.qtd_people, 3)
        write.assert_called_once()

    def test_repository_also_rejects_invalid_event_before_insert(self):
        event = Event(124, "Jantar", "Jantar", datetime(2026, 11, 20), -10, "Casa", -3)
        with patch.object(EventsRepository, "events_collection") as collection, self.assertRaises(ValueError):
            EventsRepository.create_event(event)
        collection.insert_one.assert_not_called()

    def test_invalid_recipe_quantities_never_reach_write_boundary(self):
        for quantity in INVALID_QUANTITIES:
            with self.subTest(quantity=quantity), identidade.da_requisicao(124, 124), \
                 patch.object(identidade, "executar_gravacao") as write:
                args = {**RECIPE, "ingredientes": [{"nome": "Arroz", "quantidade": quantity}]}
                self.assertTrue(mongo_recipe_tools.salvar_receita.invoke(args).startswith("FALHA:"))
                write.assert_not_called()

    def test_valid_culinary_quantities_are_preserved(self):
        def save(recipe):
            recipe.id = ObjectId()
            return recipe
        for quantity in VALID_QUANTITIES:
            with self.subTest(quantity=quantity), identidade.da_requisicao(124, 124), \
                 patch.object(RecipesRepository, "create_recipe", side_effect=save) as write:
                args = {**RECIPE, "ingredientes": [{"nome": "Arroz", "quantidade": quantity}]}
                result = json.loads(mongo_recipe_tools.salvar_receita.invoke(args))
                self.assertEqual(result["receita"]["ingredients"][0]["required_quantity"], quantity)
                write.assert_called_once()

    def test_unicode_fractions_and_separate_units(self):
        self.assertEqual(validar_quantidade_receita("\u00bd x\u00edcara"), "\u00bd x\u00edcara")
        self.assertEqual(validar_quantidade_receita("1\u00bd x\u00edcaras"), "1\u00bd x\u00edcaras")
        self.assertEqual(validar_quantidade_receita(200, "g"), "200 g")

    def test_repository_rejects_invalid_quantity_even_without_tool(self):
        recipe = Recipe("Arroz", 2, [{"name": "Arroz", "required_quantity": "-5 kg"}],
                        "Cozinhe.", 124)
        with patch.object(RecipesRepository, "recipes_collection") as collection, self.assertRaises(ValueError):
            RecipesRepository.create_recipe(recipe)
        collection.insert_one.assert_not_called()

    def test_quantity_alias_does_not_hide_invalid_primary_value(self):
        with identidade.da_requisicao(124, 124), patch.object(RecipesRepository, "create_recipe") as save:
            args = {**RECIPE, "ingredientes": [{"nome": "Arroz", "quantidade": 0,
                                               "required_quantity": "200 g"}]}
            self.assertTrue(mongo_recipe_tools.salvar_receita.invoke(args).startswith("FALHA:"))
        save.assert_not_called()

    def test_validation_failure_asks_correction_instead_of_retrying_invalid_write(self):
        envelope = json.dumps({"dominio": "receitas", "intencao": "Salvar receita",
                               "resposta": "Salvei a receita."})
        evidence = [{"ferramenta": "salvar_receita",
                     "conteudo": "FALHA: receita n\u00e3o salva. Informe quantidade positiva e unidade."}]
        with patch.object(flow, "_invocar_agente", return_value=(envelope, 1, 1, evidence)) as invoke:
            response, _, _, _ = flow._invocar_com_confirmacao(Mock(), "Salve", [], "test")
        result = json.loads(response)
        self.assertIn("quantidade positiva", result["resposta"])
        self.assertTrue(result["esclarecer"])
        self.assertIn("quantidade positiva", flow._montar_sem_modelo(response))
        invoke.assert_called_once()

    def test_missing_receipt_does_not_offer_blind_retry_for_invalid_recipe(self):
        envelope = json.dumps({"dominio": "receitas", "intencao": "Salvar receita",
                               "resposta": "Nao posso salvar esta receita."})
        with identidade.da_requisicao(124, 124), patch.object(
            flow, "_invocar_agente", return_value=(envelope, 1, 1, [])
        ):
            response, _, _, _ = flow._invocar_com_confirmacao(Mock(), "Salve", [], "test")
        self.assertIn("quantidades", json.loads(response)["resposta"])


class PrivacyPolicyTest(unittest.TestCase):
    def test_raw_pii_is_rejected_without_using_jev_or_its_scores(self):
        responses = ["O telefone da conta 125 e 11999990000.",
                     "Contato: (11) 99999-0000", "Contato: +55 11 99999-0000",
                     "E-mail: outra.conta@example.invalid", "CPF: 123.456.789-00"]
        for response in responses:
            with self.subTest(response=response), patch.object(judge, "get_jev_client") as client:
                result = judge.evaluate_jev("Mostre os dados.", response, response, "")
            self.assertEqual(result.decision, "repair")
            self.assertEqual(result.source, "code_privacy")
            client.assert_not_called()

    def test_privacy_is_checked_even_when_response_requests_clarification(self):
        envelope = {"esclarecer": "O telefone e 11999990000?", "resposta": ""}
        result = judge.deterministic_verdict(envelope, [])
        self.assertEqual(result.source, "code_privacy")

    def test_masked_contacts_refusal_and_legitimate_numbers_are_not_blocked(self):
        for response in ["Nao posso divulgar dados de outra conta.", "Telefone: [TELEFONE OMITIDO]",
                         "Estoque: 100 g de arroz.", "Jantar em 2026-11-20 as 18:00.",
                         "Receita para 4 pessoas, 30 minutos.", "Evento 20261025130000"]:
            with self.subTest(response=response):
                self.assertIsNone(judge.privacy_verdict(response))

    def test_jev_policy_explicitly_distinguishes_support_and_authorization(self):
        self.assertIn("NAO e autorizacao", judge.RULES)
        self.assertIn("outra conta", judge.QUESTIONS["segura"]["instructions"])
