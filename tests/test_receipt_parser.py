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

    def test_codigo_descricao_quantidade_preco_na_mesma_linha(self):
        linhas = [
            "# CODIGO DESCRICAO QTD UN VL UNIT VL TOTAL",
            "7891150039001 PAP H PERSONAL VIP 1 PC x 31,90 31,90",
            "7891150039001 CARVAO HATAO 1 SC x 38,98 38,98",
            "PAO MINEIRO 1 UN x 6,49 6,49",
            "3919 BATATA 0,770 KG x 9,75 7,51",
            "7891150039001 LEITE PIRAC SEMID 1 TP x 5,29 5,29",
            "7891150039001 OLEO COCO COPRA 1 PO x 20,35 20,35",
            "7891150039001 SUCO IMPERIO ULTRA 12 LT x 3,89 46,68",
            "TOTAL 164,10",
        ]
        itens = deterministic_parse(linhas)["items"]
        self.assertEqual(len(itens), 7)
        self.assertEqual(itens[0]["raw_text"], "PAP H PERSONAL VIP")
        self.assertEqual(itens[0]["quantity"], 1)
        self.assertEqual(itens[0]["unit"], "un")
        self.assertEqual(itens[0]["unit_price"], 31.90)
        self.assertEqual(itens[1]["unit"], "un")
        self.assertEqual(itens[2]["raw_text"], "PAO MINEIRO")
        self.assertEqual(itens[2]["quantity"], 1)
        self.assertEqual(itens[3]["quantity"], 0.770)
        self.assertEqual(itens[3]["unit"], "kg")
        self.assertEqual(itens[4]["unit"], "un")
        self.assertEqual(itens[5]["unit"], "un")
        self.assertEqual(itens[6]["quantity"], 12)
        self.assertEqual(itens[6]["unit"], "l")
        self.assertEqual(itens[6]["unit_price"], 3.89)

    def test_linhas_reais_da_nota_com_colunas_coladas(self):
        # Texto bruto obtido localmente pelo RapidOCR da foto enviada: o
        # cabecalho e abreviado, varios campos vem sem espacos e uma linha usa
        # o caractere de multiplicacao que o OCR nao reconheceu.
        linhas = [
            "Cod Descr. Qtd.Unid.Preco Total",
            "7696110011233PAPHPERSONALUIP1PCX31.90 31,90",
            "7898254591091CARUA0NATA01SC X38.98 38.98",
            "9100000076584PAOMINEIRO1UNX6.49 6,49",
            "7896584300246 ARR0Z SABOR0SO T1 1PC X9.79 9.79",
            "8445291144385CAPS NESCAFE BRAZIL1CXX18,90 18.90",
            "3919BATATA0.770 KGX 9.75 7.51",
            "789812G114027CHEIROU S0U D TERRA1 PO X5.95 5.95",
            "7898215151760LEITELVPIRACSEMID1TP�5,29",
            "43014BACONHSADIAEMB0,336KGX28.90 9.71",
            "7896112310013HANT TAUBATE C/S1PO X11,99 11.99",
            "78985960805740LCOCO COPRA S/SAB 1POX20,35 20,35",
            "7894000050034MAI0N HELLMANNS TRAD1P0 X10,49 10,49",
            "7894000050034MAI0NHELLHANNS TRAD1PO X 10.49 10.49",
            "7894900701517 REFC0CA C0LA S/ACU 1 PI X12.49 12.49",
            "7898915949940 CUJ IHPERI0 ULTRA 12LTX 3.89 46.68",
        ]
        parsed = deterministic_parse(linhas)
        itens = parsed["items"]
        self.assertEqual(len(itens), 14)  # As duas linhas iguais de maionese sao agrupadas.
        self.assertAlmostEqual(items_sum(itens), 247.01, places=2)
        self.assertEqual(itens[0]["quantity"], 1)
        self.assertEqual(itens[0]["unit_price"], 31.90)
        self.assertEqual(itens[5]["raw_text"], "BATATA")
        self.assertEqual(itens[5]["quantity"], 0.770)
        self.assertEqual(itens[8]["raw_text"], "BACONHSADIAEMB")
        self.assertEqual(itens[11]["quantity"], 2)
        self.assertEqual(itens[-1]["quantity"], 12)
        self.assertEqual(itens[-1]["unit"], "l")

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
