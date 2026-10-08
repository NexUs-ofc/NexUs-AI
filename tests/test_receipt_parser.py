import unittest

from app.tools.receipt_parser import (
    deterministic_parse,
    ean_candidates,
    ean_valid,
    items_sum,
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


if __name__ == "__main__":
    unittest.main()
