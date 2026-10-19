import unittest
from datetime import date

from app.tools.date_tools import _resolver


class QuantidadeRelativaTest(unittest.TestCase):
    hoje = date(2026, 10, 18)

    def test_tres_meses_sao_tres_meses_de_calendario(self):
        self.assertEqual(_resolver("daqui a 3 meses", self.hoje), date(2027, 1, 18))

    def test_numero_por_extenso(self):
        self.assertEqual(_resolver("tres meses", self.hoje), date(2027, 1, 18))

    def test_dia_31_cai_no_ultimo_dia_do_mes_de_destino(self):
        self.assertEqual(_resolver("1 mes", date(2026, 1, 31)), date(2026, 2, 28))

    def test_semanas_e_dias(self):
        self.assertEqual(_resolver("2 semanas", self.hoje), date(2026, 11, 1))
        self.assertEqual(_resolver("em 10 dias", self.hoje), date(2026, 10, 28))

    def test_um_ano(self):
        self.assertEqual(_resolver("1 ano", self.hoje), date(2027, 10, 18))

    def test_dia_do_mes_continua_funcionando(self):
        self.assertEqual(_resolver("dia 20", self.hoje), date(2026, 10, 20))


if __name__ == "__main__":
    unittest.main()
