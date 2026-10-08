import unittest

from app.bases.shelf_life import DEFAULT_CATEGORIES, is_storable_food
from app.core.receipt_agent import _build_response

COMIDA = ["Hortifruti", "Carnes e Peixes", "Frios e Laticínios", "Padaria",
          "Congelados", "Mercearia", "Bebidas", "Doces e Snacks", "Outros"]
NAO_COMIDA = ["Higiene", "Limpeza", "Pet"]


def item(nome, categoria, preco=1.0, qtd=1):
    return {
        "raw_text": nome,
        "name": nome,
        "ean": "7891150039001",
        "ean_candidates": [],
        "quantity": qtd,
        "unit": "un",
        "unit_price": preco,
        "category": categoria,
    }


class CategoriaTests(unittest.TestCase):
    def test_comida_fica(self):
        for c in COMIDA:
            self.assertTrue(is_storable_food(c), c)

    def test_nao_comida_sai(self):
        for c in NAO_COMIDA:
            self.assertFalse(is_storable_food(c), c)

    def test_acento_e_caixa_nao_importam(self):
        self.assertFalse(is_storable_food("LIMPEZA"))
        self.assertFalse(is_storable_food("higiene"))
        self.assertFalse(is_storable_food(" Pet "))

    def test_sem_categoria_fica(self):
        self.assertTrue(is_storable_food(None))
        self.assertTrue(is_storable_food(""))

    def test_todas_as_categorias_padrao_sao_decidiveis(self):
        for c in DEFAULT_CATEGORIES:
            self.assertIsInstance(is_storable_food(c), bool)


class RespostaTests(unittest.TestCase):
    def setUp(self):
        self.itens = [
            item("Amaciante Comfort 500ml", "Limpeza", 6.15, 2),
            item("Chocolate Lacta 20g", "Doces e Snacks", 1.69, 1),
        ]
        self.resp = _build_response(
            {"store": "Bistek", "total": 13.99}, self.itens, "ocr+llm", 0.8, [], DEFAULT_CATEGORIES
        )

    def test_so_alimento_volta(self):
        self.assertEqual([i.name for i in self.resp.items], ["Chocolate Lacta 20g"])

    def test_descartado_e_nomeado(self):
        self.assertEqual(self.resp.discarded, ["Amaciante Comfort 500ml"])

    def test_soma_usa_tudo_que_foi_lido(self):
        self.assertAlmostEqual(self.resp.items_total, 13.99, places=2)

    def test_soma_bate_com_o_total_sem_aviso_falso(self):
        self.assertFalse(any("não bate" in w for w in self.resp.warnings))

    def test_avisa_o_que_ficou_de_fora(self):
        self.assertTrue(any("Amaciante Comfort 500ml" in w for w in self.resp.warnings))

    def test_nota_so_de_nao_alimento_volta_vazia(self):
        resp = _build_response(
            {"total": 12.30}, [item("Sabao em po", "Limpeza", 6.15, 2)], "ocr", 0.8, [], DEFAULT_CATEGORIES
        )

        self.assertEqual(resp.items, [])
        self.assertEqual(resp.discarded, ["Sabao em po"])

    def test_item_sem_categoria_nao_e_descartado(self):
        resp = _build_response(
            {"total": 1.0}, [item("Item não identificado", None, 1.0, 1)], "ocr", 0.8, [], DEFAULT_CATEGORIES
        )

        self.assertEqual(len(resp.items), 1)
        self.assertEqual(resp.discarded, [])


if __name__ == "__main__":
    unittest.main()
