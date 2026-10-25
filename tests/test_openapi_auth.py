"""O Swagger deve separar as chaves do app e do painel, em qualquer ordem."""

import unittest
from typing import Annotated

from fastapi import Depends, FastAPI

from app.auth.admin_key_validator import validate_admin_key
from app.auth.dependencies import get_current_user
from app.config import API_KEY_HEADER


def chat(user: Annotated[dict, Depends(get_current_user)]):
    return {}


def admin(key: Annotated[str, Depends(validate_admin_key)]):
    return {}


class OpenApiAuthTest(unittest.TestCase):
    def test_chaves_nao_se_sobrescrevem_na_documentacao(self):
        for admin_primeiro in (False, True):
            with self.subTest(admin_primeiro=admin_primeiro):
                app = FastAPI()
                rotas = [("/chat/", chat), ("/admin/session", admin)]
                if admin_primeiro:
                    rotas.reverse()
                for path, endpoint in rotas:
                    app.add_api_route(path, endpoint)

                schema = app.openapi()
                esquemas = schema["components"]["securitySchemes"]
                self.assertEqual(esquemas["AppApiKey"]["name"], API_KEY_HEADER)
                self.assertEqual(esquemas["AdminApiKey"]["name"], "X-Admin-Key")
                self.assertEqual(esquemas["AppApiKey"]["in"], "header")
                self.assertEqual(esquemas["AdminApiKey"]["in"], "header")

                chat_auth = schema["paths"]["/chat/"]["get"]["security"]
                admin_auth = schema["paths"]["/admin/session"]["get"]["security"]
                self.assertIn({"AppApiKey": []}, chat_auth)
                self.assertIn({"HTTPBearer": []}, chat_auth)
                self.assertNotIn({"AdminApiKey": []}, chat_auth)
                self.assertEqual(admin_auth, [{"AdminApiKey": []}])
