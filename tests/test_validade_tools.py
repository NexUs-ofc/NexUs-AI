import unittest
from typing import ClassVar

from app.tools.validade_tools import prazo_no_trecho, validar_escolha


class PrazoNoTrechoTest(unittest.TestCase):
    def test_prazo_unico(self):
        self.assertEqual(prazo_no_trecho("A maçã dura 30 dias na geladeira.", "maçã", "geladeira"), 30)

    def test_plural_casa_com_singular(self):
        self.assertEqual(prazo_no_trecho("Maçãs duram de 4 a 6 semanas refrigeradas.", "maçã", "geladeira"), 28)

    def test_faixa_usa_o_limite_de_baixo(self):
        # Trecho real (UOL) que a regra anterior descartava.
        trecho = (
            "Quando mantido em temperatura ambiente, o tomate pode ser consumido "
            "de três a sete dias com a mesma firmeza, cor, textura, sabor e aparência."
        )
        self.assertEqual(prazo_no_trecho(trecho, "tomate", "temperatura ambiente"), 3)

    def test_faixa_larga_demais_e_descartada(self):
        self.assertIsNone(prazo_no_trecho("Maçãs duram de 1 a 6 meses na geladeira.", "maçã", "geladeira"))

    def test_tabela_sem_o_local_de_guarda_nao_vale(self):
        # Trecho real: o "30 dias" e do extrato de tomate, numa tabela de varios itens.
        trecho = "horas) EXTRATO DE TOMATE 30 dias 90 dias BISCOITOS 30 dias CEBOLA DESCASCADA 3 dias"
        self.assertIsNone(prazo_no_trecho(trecho, "tomate", "temperatura ambiente"))

    def test_frase_de_outro_produto_nao_vale(self):
        trecho = "A banana dura 5 dias na geladeira. A maçã é rica em fibras."
        self.assertIsNone(prazo_no_trecho(trecho, "maçã", "geladeira"))

    def test_com_dois_prazos_vale_o_do_local_pedido(self):
        # Trecho real (The Conversation).
        trecho = (
            "Maçãs têm prazo de validade de cerca de uma semana em temperatura "
            "ambiente e de três a quatro semanas na geladeira."
        )
        self.assertEqual(prazo_no_trecho(trecho, "maçã", "geladeira"), 21)
        self.assertEqual(prazo_no_trecho(trecho, "maçã", "temperatura ambiente"), 7)

    def test_numero_por_extenso(self):
        self.assertEqual(prazo_no_trecho("O tomate dura uma semana fora da geladeira.", "tomate", "temperatura ambiente"), 7)


class ValidarEscolhaTest(unittest.TestCase):
    resultados: ClassVar[list[dict]] = [
        {"url": "https://a.org", "content": "Banana passa: 360 dias em temperatura ambiente."},
        {"url": "https://b.org", "content": "Guardada na geladeira, a maçã dura 4 semanas. Lave antes de comer."},
    ]

    def test_frase_literal_da_fonte_vale(self):
        escolha = validar_escolha(
            self.resultados, "maçã", "geladeira",
            {"indice": 1, "frase": "Guardada na geladeira, a maçã dura 4 semanas."},
        )
        self.assertEqual(escolha["dias"], 28)
        self.assertEqual(escolha["fonte"], "https://b.org")

    def test_frase_inventada_nao_vale(self):
        escolha = validar_escolha(
            self.resultados, "maçã", "geladeira",
            {"indice": 1, "frase": "A maçã dura 60 dias na geladeira."},
        )
        self.assertIsNone(escolha["dias"])

    def test_numero_vem_da_frase_e_nao_do_modelo(self):
        escolha = validar_escolha(
            self.resultados, "maçã", "geladeira",
            {"indice": 1, "frase": "Guardada na geladeira, a maçã dura 4 semanas.", "dias": 90},
        )
        self.assertEqual(escolha["dias"], 28)

    def test_indice_fora_da_lista_ou_nulo(self):
        self.assertIsNone(validar_escolha(self.resultados, "maçã", "geladeira", {"indice": 7, "frase": "x"})["dias"])
        self.assertIsNone(validar_escolha(self.resultados, "maçã", "geladeira", {"indice": None})["dias"])

    def test_frase_sem_o_local_pedido_nao_vale(self):
        escolha = validar_escolha(
            self.resultados, "banana", "geladeira",
            {"indice": 0, "frase": "Banana passa: 360 dias em temperatura ambiente."},
        )
        self.assertIsNone(escolha["dias"])


if __name__ == "__main__":
    unittest.main()
