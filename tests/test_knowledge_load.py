import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.knowledge_load import sincronizar


class Client:
    def __init__(self):
        self.points = {"antigo": {"page_content": "Resposta antiga"}}
        self.deleted = []
        self.uploads = 0
        self.fail_upload = None

    def collection_exists(self, _name):
        return True

    def scroll(self, **_kwargs):
        return [SimpleNamespace(id=i) for i in self.points], None

    def upsert(self, points, **_kwargs):
        self.uploads += 1
        if self.uploads == self.fail_upload:
            raise RuntimeError("upload interrompido")
        self.points.update({p.id: p.payload for p in points})

    def delete(self, points_selector, **_kwargs):
        self.deleted.extend(points_selector.points)
        for i in points_selector.points:
            self.points.pop(i, None)

    def count(self, **_kwargs):
        return SimpleNamespace(count=len(self.points))


class Embeddings:
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


class KnowledgeLoadTest(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.docs = [
            {"page_content": "Pergunta: inclusão? Resposta: pelas telas do app.",
             "metadata": {"resposta_pura": "Pelas telas do app."}},
            {"page_content": "O chat consulta e remove produtos autorizados.",
             "metadata": {}},
        ]

    @patch("scripts.knowledge_load.time.sleep")
    def test_substitui_obsoletos_e_repetir_nao_duplica(self, _sleep):
        ids = sincronizar(self.docs, "nexus_faqs", self.client, Embeddings(), lote=1)
        self.assertEqual(set(self.client.points), set(ids))
        self.assertEqual(self.client.deleted, ["antigo"])
        repetidos = sincronizar(self.docs, "nexus_faqs", self.client, Embeddings())
        self.assertEqual(repetidos, ids)
        self.assertEqual(len(self.client.points), 2)

    @patch("scripts.knowledge_load.time.sleep")
    def test_falha_no_segundo_lote_preserva_a_base_anterior(self, _sleep):
        self.client.fail_upload = 2
        with self.assertRaisesRegex(RuntimeError, "interrompido"):
            sincronizar(self.docs, "nexus_faqs", self.client, Embeddings(), lote=1)
        self.assertIn("antigo", self.client.points)
        self.assertEqual(self.client.deleted, [])

    def test_base_vazia_nao_apaga_nada(self):
        with self.assertRaises(ValueError):
            sincronizar([], "nexus_faqs", self.client, Embeddings())
        self.assertEqual(self.client.uploads, 0)
        self.assertEqual(self.client.deleted, [])

    def test_nao_permite_alterar_memoria_dos_usuarios(self):
        with self.assertRaises(ValueError):
            sincronizar(self.docs, "session_summary", self.client, Embeddings())
        self.assertEqual(self.client.uploads, 0)
