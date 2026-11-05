"""Testes da integração PhotoBooth/GreenAPI (sem chamadas externas reais)."""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controller import photobooth as rota
from app.services.greenapi_client import (
    GreenApiClient,
    GreenApiNotReady,
    GreenApiSettings,
)

JPEG = b"\xff\xd8\xff" + b"photo-test"
app = FastAPI()
app.include_router(rota.router)


class FakeGreenApi:
    def __init__(self):
        self.photo_args = None

    async def get_instance_state(self):
        return "authorized"

    async def send_photo(self, *, phone, name, image):
        self.photo_args = {"phone": phone, "name": name, "image": image}
        return "message-123"


class TestPhotoBoothRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"PHOTOBOOTH_API_KEY": "kiosk-test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _request(self, *, headers=None, **data):
        values = {
            "name": "Ana Souza",
            "phone": "(11) 99999-9999",
            "consent": "true",
        }
        values.update(data)
        return self.client.post(
            "/photobooth/send",
            headers=headers or {"X-PhotoBooth-Key": "kiosk-test-key"},
            data=values,
            files={"photo": ("final.jpg", JPEG, "image/jpeg")},
        )

    def test_envia_foto_composta_com_nome_e_normaliza_telefone_brasileiro(self):
        client = FakeGreenApi()
        with patch.object(rota, "GreenApiClient", return_value=client):
            response = self._request()

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"status": "queued", "idMessage": "message-123"})
        self.assertEqual(
            client.photo_args,
            {"phone": "5511999999999", "name": "Ana Souza", "image": JPEG},
        )

    def test_nao_envia_sem_consentimento(self):
        response = self._request(consent="false")
        self.assertEqual(response.status_code, 403)

    def test_recusa_chave_invalida(self):
        response = self._request(headers={"X-PhotoBooth-Key": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_recusa_upload_que_nao_e_jpeg(self):
        response = self.client.post(
            "/photobooth/send",
            headers={"X-PhotoBooth-Key": "kiosk-test-key"},
            data={"name": "Ana Souza", "phone": "11999999999", "consent": "true"},
            files={"photo": ("final.png", b"not-jpeg", "image/png")},
        )
        self.assertEqual(response.status_code, 415)

    def test_instancia_desconectada_nao_gera_envio(self):
        client = FakeGreenApi()
        async def disconnected(**_kwargs):
            raise GreenApiNotReady("notAuthorized")
        client.send_photo = disconnected
        with patch.object(rota, "GreenApiClient", return_value=client):
            response = self._request()
        self.assertEqual(response.status_code, 503)


class TestGreenApiClient(unittest.TestCase):
    def test_consulta_estado_e_envia_multipart_com_caption(self):
        requests = []
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/getStateInstance/token-test"):
                return httpx.Response(200, json={"stateInstance": "authorized"})
            self.assertTrue(request.url.path.endswith("/sendFileByUpload/token-test"))
            body = request.read().decode("utf-8", errors="replace")
            self.assertIn("5511999999999@c.us", body)
            self.assertIn("Obrigado por visitar nosso stand Ana Souza!💜", body)
            self.assertIn("expotech-2026.jpg", body)
            return httpx.Response(200, json={"idMessage": "green-456"})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        def factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        settings = GreenApiSettings(
            api_url="https://7107.api.greenapi.com",
            media_url="https://7107.api.greenapi.com",
            instance_id="instance-test",
            token="token-test",
        )
        with patch("app.services.greenapi_client.httpx.AsyncClient", side_effect=factory):
            message_id = asyncio.run(
                GreenApiClient(settings).send_photo(
                    phone="5511999999999",
                    name="Ana Souza",
                    image=JPEG,
                )
            )

        self.assertEqual(message_id, "green-456")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[1].method, "POST")

    def test_nao_envia_se_instancia_nao_estiver_autorizada(self):
        requests = []
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"stateInstance": "notAuthorized"})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        def factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        settings = GreenApiSettings(
            api_url="https://7107.api.greenapi.com",
            media_url="https://7107.api.greenapi.com",
            instance_id="instance-test",
            token="token-test",
        )
        with patch("app.services.greenapi_client.httpx.AsyncClient", side_effect=factory), self.assertRaises(GreenApiNotReady):
            asyncio.run(
                GreenApiClient(settings).send_photo(
                    phone="5511999999999",
                    name="Ana Souza",
                    image=JPEG,
                )
            )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")


if __name__ == "__main__":
    unittest.main()

