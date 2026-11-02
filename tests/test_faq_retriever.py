import unittest
from unittest.mock import patch

from app.tools import faq_tools


class FAQRetrieverTest(unittest.TestCase):
    def test_retorna_so_respostas_da_colecao_faq(self):
        with patch.object(faq_tools.faq_repo, "buscar_respostas_faq", return_value=["Resposta oficial"]):
            resposta = faq_tools.faq_retriever.invoke({"question": "pergunta"})

        self.assertEqual(resposta, "- Resposta oficial")
        self.assertFalse(hasattr(faq_tools, "doc_repo"))

    def test_falha_de_consulta_nao_tenta_documentacao_secundaria(self):
        with patch.object(faq_tools.faq_repo, "buscar_respostas_faq", side_effect=RuntimeError("offline")):
            resposta = faq_tools.faq_retriever.invoke({"question": "pergunta"})

        self.assertIn("FALHA:", resposta)
