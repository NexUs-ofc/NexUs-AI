"""Testes de contrato da API HTTP do Ceris.

Os testes substituem o executor do fluxo por um mock. Assim, validamos a
camada controller e o contrato OpenAPI sem depender de LLMs ou bancos.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_healthcheck(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": 200, "msg": "Ceris rodando com sucesso!"},
        )

    def test_openapi_maps_public_endpoints(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/", paths)
        self.assertIn("get", paths["/"])
        self.assertIn("/chat", paths)
        self.assertIn("post", paths["/chat"])

    @patch("app.controller.chat.executar_chat")
    def test_chat_returns_response_and_generated_session(self, executar_chat) -> None:
        # O mock impede que este teste acione Groq, MongoDB ou PostgreSQL.
        executar_chat.return_value = {
            "resposta": "Receita de teste",
            "session_id": "session-generated",
        }

        response = self.client.post(
            "/chat",
            json={"mensagem": "Quero uma receita com arroz"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "resposta": "Receita de teste",
                "session_id": "session-generated",
            },
        )
        executar_chat.assert_called_once_with(
            mensagem="Quero uma receita com arroz",
            session_id=None,
            household_account_id=1,
            account_id=1,
        )

    @patch("app.controller.chat.executar_chat")
    def test_chat_reuses_session_id(self, executar_chat) -> None:
        # Este teste registra o contrato esperado para continuidade da conversa.
        executar_chat.return_value = {
            "resposta": "Continuação de teste",
            "session_id": "session-existing",
        }

        response = self.client.post(
            "/chat",
            json={
                "mensagem": "Agora use a mesma conversa",
                "session_id": "session-existing",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], "session-existing")
        executar_chat.assert_called_once_with(
            mensagem="Agora use a mesma conversa",
            session_id="session-existing",
            household_account_id=1,
            account_id=1,
        )

    def test_chat_requires_message(self) -> None:
        response = self.client.post("/chat", json={})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()