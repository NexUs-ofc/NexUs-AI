import unittest

from app.tools.receipt_parser import (
    clean_desc,
    deterministic_parse,
    ean_candidates,
    ean_valid,
    items_sum,
    needs_deep_pass,
    split_index_ean,
)

OCR_LINES = [
    "OISTEK SUPERNERCADOS LTDA",
    "CNPJ: 83.261.420/0017-16",
    "01/04/2016 12:45:48.CCF:185243 C00 :28",
    "OUPOM.FISCAL",
    "ITEN CODIGO DESCRICAO ST: IAT UL: ITE!",
    "QTD.  UN UL UNIT RS",
    "17891150039001 AMAC.COMFORT 500ML",
    "1 UN X 6,15 F1: T 6,",
    "27891150039001AMAC.COMFORT 500ME",
    "1- UN.X.6, 15 * Ft T 6,",
    "CHOC.LACTA 20G/25G DIA",
    "3 7622300662282 FT.T 1,",
    "1 UN X 1,69",
    "TOTALRS 13.99",
]


class EanTests(unittest.TestCase):
    def test_valid_ean(self):
        self.assertTrue(ean_valid("7891150039001"))
        self.assertTrue(ean_valid("7622300862282"))

    def test_invalid_ean(self):
        self.assertFalse(ean_valid("7622300662282"))
        self.assertFalse(ean_valid("78911009001"))
        self.assertFalse(ean_valid(None))

    def test_split_index_glued_to_ean(self):
        self.assertEqual(split_index_ean("17891150039001", 1), (1, "7891150039001"))

    def test_candidates_include_real_code(self):
        self.assertIn("7622300862282", ean_candidates("7622300662282"))


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.parsed = deterministic_parse(OCR_LINES)

    def test_header(self):
        self.assertEqual(self.parsed["cnpj"], "83.261.420/0017-16")
        self.assertEqual(str(self.parsed["purchase_date"]), "2016-04-01")
        self.assertEqual(self.parsed["total"], 13.99)

    def test_duplicate_lines_are_merged(self):
        amac = self.parsed["items"][0]
        self.assertEqual(amac["ean"], "7891150039001")
        self.assertEqual(amac["quantity"], 2)

    def test_orphan_description_is_attached(self):
        choc = self.parsed["items"][1]
        self.assertEqual(choc["raw_text"], "CHOC.LACTA 20G/25G DIA")
        self.assertIsNone(choc["ean"])
        self.assertEqual(choc["unit_price"], 1.69)

    def test_sum_matches_total(self):
        self.assertAlmostEqual(items_sum(self.parsed["items"]), self.parsed["total"], places=2)

    def test_qtd_total_de_itens_depois_dos_produtos_nao_some_com_eles(self):
        # Toda NFC-e tem "QTD. TOTAL DE ITENS" depois dos produtos; contada como
        # cabecalho, a nota voltava sem item nenhum.
        linhas = [
            "SUPERMERCADO BOM PRECO LTDA",
            "# CODIGO DESCRICAO QTD UN VL UNIT VL TOTAL",
            "001 7891150039001 AMAC.COMFORT 500ML",
            "1 UN X 6,15 6,15",
            "QTD. TOTAL DE ITENS 1",
            "VALOR TOTAL R$ 6,15",
        ]
        itens = deterministic_parse(linhas)["items"]
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["ean"], "7891150039001")


class LimpezaTests(unittest.TestCase):
    def test_zero_colado_em_letra_vira_o(self):
        self.assertEqual(clean_desc("ARR0Z BRANC0 5KG"), "ARROZ BRANCO 5KG")
        self.assertEqual(clean_desc("CAFE T0RRAD0 500G"), "CAFE TORRADO 500G")

    def test_numero_com_zero_fica_como_esta(self):
        self.assertEqual(clean_desc("LEITE 1L 500ML 1000G"), "LEITE 1L 500ML 1000G")


class PassadaFundaTests(unittest.TestCase):
    def test_ean_ilegivel_nao_dispara(self):
        parsed = {
            "items": [{"raw_text": "ARROZ", "ean": None, "raw_ean": "7896004000207", "quantity": 1, "unit_price": 27.9}],
            "total": 27.9,
        }
        self.assertFalse(needs_deep_pass(parsed))

    def test_soma_que_nao_fecha_dispara(self):
        parsed = {
            "items": [{"raw_text": "ARROZ", "ean": None, "raw_ean": None, "quantity": 1, "unit_price": 27.9}],
            "total": 50.0,
        }
        self.assertTrue(needs_deep_pass(parsed))


if __name__ == "__main__":
    unittest.main()
