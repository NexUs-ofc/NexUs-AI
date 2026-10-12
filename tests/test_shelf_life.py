"""
Validade por categoria e o filtro de "isto é comida?".

Decide o que entra no estoque a partir da nota fiscal: errar aqui põe sabão em
pó na despensa ou joga fora um alimento válido.
"""

import unittest

from app.core.shelf_life import (
    DEFAULT_CATEGORIES,
    FALLBACK_DAYS,
    NON_FOOD_CATEGORIES,
    SHELF_LIFE_DAYS,
    is_storable_food,
    shelf_life_days,
)


class TestValidadePorCategoria(unittest.TestCase):
    def test_categoria_conhecida_usa_a_tabela(self):
        self.assertEqual(shelf_life_days("Hortifruti"), 7)
        self.assertEqual(shelf_life_days("Carnes e Peixes"), 3)
        self.assertEqual(shelf_life_days("Mercearia"), 180)

    def test_acento_e_caixa_nao_importam(self):
        for escrito in ("Frios e Laticínios", "frios e laticinios",
                        "FRIOS E LATICINIOS", "  Frios e Laticínios  "):
            with self.subTest(escrito=escrito):
                self.assertEqual(shelf_life_days(escrito), 10)

    def test_toda_categoria_padrao_tem_entrada_na_tabela(self):
        """Se alguem acrescentar categoria e esquecer a validade, cai aqui."""

        from app.core.shelf_life import _key

        for categoria in DEFAULT_CATEGORIES:
            with self.subTest(categoria=categoria):
                self.assertIn(
                    _key(categoria),
                    SHELF_LIFE_DAYS,
                    f"{categoria} nao tem validade declarada",
                )

    def test_categoria_desconhecida_usa_o_palpite_do_modelo(self):
        self.assertEqual(shelf_life_days("Categoria Inventada", llm_guess=12), 12)

    def test_a_tabela_tem_prioridade_sobre_o_palpite(self):
        self.assertEqual(shelf_life_days("Hortifruti", llm_guess=999), 7)

    def test_palpite_absurdo_e_limitado(self):
        self.assertEqual(shelf_life_days("Inventada", llm_guess=99999), 1095)
        self.assertEqual(shelf_life_days("Inventada", llm_guess=0), FALLBACK_DAYS)
        self.assertEqual(shelf_life_days("Inventada", llm_guess=-5), 1)

    def test_sem_categoria_e_sem_palpite_cai_no_fallback(self):
        self.assertEqual(shelf_life_days(None), FALLBACK_DAYS)
        self.assertEqual(shelf_life_days(""), FALLBACK_DAYS)


class TestFiltroDeAlimento(unittest.TestCase):
    def test_comida_e_armazenavel(self):
        for categoria in ("Hortifruti", "Carnes e Peixes", "Mercearia",
                          "Bebidas", "Padaria", "Congelados"):
            with self.subTest(categoria=categoria):
                self.assertTrue(is_storable_food(categoria))

    def test_nao_comida_e_recusada(self):
        for categoria in ("Higiene", "Limpeza", "Pet", "Bazar",
                          "Utilidades", "Vestuario", "Farmacia"):
            with self.subTest(categoria=categoria):
                self.assertFalse(is_storable_food(categoria))

    def test_acento_e_caixa_nao_driblam_o_filtro(self):
        for escrito in ("LIMPEZA", "limpeza", "  Limpeza ", "Vestuário"):
            with self.subTest(escrito=escrito):
                self.assertFalse(is_storable_food(escrito))

    def test_sem_categoria_passa(self):
        """Na duvida, aceita: o usuario corrige mais facil do que descobre o
        que sumiu."""

        self.assertTrue(is_storable_food(None))
        self.assertTrue(is_storable_food(""))

    def test_as_duas_tabelas_nao_se_contradizem(self):
        """Categoria nao-comida nao pode ter validade de alimento."""

        comida_com_validade = {
            k for k in SHELF_LIFE_DAYS if k not in NON_FOOD_CATEGORIES
        }

        for chave in NON_FOOD_CATEGORIES & set(SHELF_LIFE_DAYS):
            with self.subTest(chave=chave):
                self.assertFalse(is_storable_food(chave))

        self.assertTrue(comida_com_validade)


if __name__ == "__main__":
    unittest.main()
