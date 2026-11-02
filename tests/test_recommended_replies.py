import unittest

from pydantic import ValidationError

from app.core.recommended_replies import (
    RESPOSTAS_COMUNS,
    prever_respostas_recomendadas,
)
from app.model.dto.chat_response import ChatResponse


class RecommendedRepliesTest(unittest.TestCase):
    def test_catalogo_tem_cerca_de_trinta_respostas_mocadas(self):
        self.assertGreaterEqual(len(RESPOSTAS_COMUNS), 30)
        self.assertLessEqual(len(RESPOSTAS_COMUNS), 35)

    def test_sugere_opcoes_para_esclarecimento_de_duracao(self):
        result = prever_respostas_recomendadas(
            "Vou criar um evento.",
            "Qual será a duração do evento?",
            "eventos",
            {"esclarecer": "Qual será a duração do evento?"},
        )

        self.assertEqual(result, ["1 hora", "2 horas", "3 horas"])

    def test_sugere_de_uma_a_tres_acoes_para_receita_com_itens_faltantes(self):
        result = prever_respostas_recomendadas(
            "Faça uma receita com Nesquik.",
            "Aqui está a receita.",
            "receitas",
            {"receita": {"porcoes": 1, "ingredientes_faltantes": ["leite"]}},
        )

        self.assertGreaterEqual(len(result), 1)
        self.assertLessEqual(len(result), 3)
        self.assertIn("Monte uma lista de compras", result)
        self.assertIn("Salve essa receita", result)

    def test_resposta_atual_da_ia_tambem_muda_o_ranking(self):
        result = prever_respostas_recomendadas(
            "Me dê uma sugestão.",
            "Faltam leite e açúcar para comprar para preparar essa receita.",
            "receitas",
            {"receita": {"porcoes": 2, "ingredientes_faltantes": ["leite", "açúcar"]}},
        )

        self.assertEqual(result[0], "Monte uma lista de compras")

    def test_sugestoes_de_estoque_sao_perguntas_sem_escrita(self):
        result = prever_respostas_recomendadas(
            "O que tenho no estoque?",
            "Você tem leite e arroz no estoque.",
            "estoque",
        )

        self.assertEqual(len(result), 3)
        self.assertIn("O que está perto de vencer?", result)
        self.assertIn("O que está em falta no estoque?", result)

    def test_a_mensagem_atual_pesa_mais_que_contagens_antigas_da_sessao(self):
        historico = [
            {"role": "user", "content": "O que tenho no estoque?"},
            {"role": "assistant", "content": "Você tem arroz e leite."},
        ] * 4
        result = prever_respostas_recomendadas(
            "Quais produtos estão vencendo?",
            "Você tem leite e arroz no estoque.",
            "estoque",
            historico=historico,
        )

        self.assertEqual(result[0], "O que está perto de vencer?")

    def test_omite_campo_quando_nao_existe_proximo_passo_util(self):
        self.assertIsNone(prever_respostas_recomendadas(
            "Oi", "Olá! Como posso ajudar?", "saudacao",
        ))
        self.assertIsNone(prever_respostas_recomendadas(
            "Faça uma receita", "A IA está temporariamente indisponível.", "receitas",
        ))

    def test_nao_ultrapassa_tres_opcoes(self):
        result = prever_respostas_recomendadas(
            "Crie um evento.",
            "Qual é o local e quantas pessoas participarão?",
            "eventos",
            {"esclarecer": "Qual é o endereço do evento?"},
        )

        self.assertLessEqual(len(result), 3)
        self.assertEqual(result, ["Na minha casa", "No endereço cadastrado", "Em outro endereço"])

    def test_contrato_http_omite_lista_vazia_e_limita_a_tres(self):
        sem_sugestoes = ChatResponse(resposta="Olá", session_id="abc")
        self.assertNotIn("respostas_recomendadas", sem_sugestoes.model_dump(exclude_none=True))

        com_sugestoes = ChatResponse(
            resposta="Receita pronta", session_id="abc",
            respostas_recomendadas=["Salve essa receita", "Faça outra receita"],
        )
        self.assertEqual(len(com_sugestoes.respostas_recomendadas), 2)
        with self.assertRaises(ValidationError):
            ChatResponse(
                resposta="Receita pronta",
                respostas_recomendadas=["A", "B", "C", "D"],
            )


if __name__ == "__main__":
    unittest.main()
