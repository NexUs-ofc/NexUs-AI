"""Integração direta com os endpoints oficiais da GREEN-API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


class GreenApiError(RuntimeError):
    """Falha segura da integração Green API, sem incluir URL/token na mensagem."""


class GreenApiNotConfigured(GreenApiError):
    pass


class GreenApiNotReady(GreenApiError):
    def __init__(self, state: str):
        self.state = state
        super().__init__("A instância Green API não está autorizada.")


@dataclass(frozen=True)
class GreenApiSettings:
    api_url: str
    media_url: str
    instance_id: str
    token: str = field(repr=False)
    timeout_seconds: float = 20.0

    @classmethod
    def from_environment(cls) -> GreenApiSettings:
        values = {
            "GREENAPI_API_URL": os.getenv("GREENAPI_API_URL", "").strip(),
            "GREENAPI_MEDIA_URL": os.getenv("GREENAPI_MEDIA_URL", "").strip(),
            "GREENAPI_ID_INSTANCE": os.getenv("GREENAPI_ID_INSTANCE", "").strip(),
            "GREENAPI_API_TOKEN_INSTANCE": os.getenv("GREENAPI_API_TOKEN_INSTANCE", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise GreenApiNotConfigured(
                "Configuração Green API ausente: " + ", ".join(missing)
            )

        for key in ("GREENAPI_API_URL", "GREENAPI_MEDIA_URL"):
            parsed = urlparse(values[key])
            if parsed.scheme != "https" or not parsed.netloc:
                raise GreenApiNotConfigured(f"{key} deve ser uma URL HTTPS.")

        timeout = os.getenv("GREENAPI_TIMEOUT_SECONDS", "20").strip()
        try:
            timeout_seconds = min(max(float(timeout), 1.0), 60.0)
        except ValueError as exc:
            raise GreenApiNotConfigured(
                "GREENAPI_TIMEOUT_SECONDS deve ser um número entre 1 e 60."
            ) from exc

        return cls(
            api_url=values["GREENAPI_API_URL"].rstrip("/"),
            media_url=values["GREENAPI_MEDIA_URL"].rstrip("/"),
            instance_id=values["GREENAPI_ID_INSTANCE"],
            token=values["GREENAPI_API_TOKEN_INSTANCE"],
            timeout_seconds=timeout_seconds,
        )

    def endpoint(self, base_url: str, method: str) -> str:
        return (
            f"{base_url}/waInstance{self.instance_id}/"
            f"{method}/{self.token}"
        )


class GreenApiClient:
    def __init__(self, settings: GreenApiSettings | None = None):
        self.settings = settings or GreenApiSettings.from_environment()

    async def get_instance_state(self) -> str:
        url = self.settings.endpoint(self.settings.api_url, "getStateInstance")
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise GreenApiError("Não foi possível consultar o estado da instância Green API.") from exc

        if not response.is_success:
            raise GreenApiError(
                f"Green API respondeu HTTP {response.status_code} ao consultar a instância."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GreenApiError("Green API retornou uma resposta inválida.") from exc
        if not isinstance(payload, dict):
            raise GreenApiError("Green API retornou uma resposta inválida.")
        return str(payload.get("stateInstance", "unknown"))

    async def send_photo(self, *, phone: str, name: str, image: bytes) -> str:
        state = await self.get_instance_state()
        if state != "authorized":
            raise GreenApiNotReady(state)

        chat_id = f"{phone}@c.us"
        caption = f"Obrigado por visitar nosso stand {name}!💜"
        url = self.settings.endpoint(self.settings.media_url, "sendFileByUpload")
        form = {
            "chatId": chat_id,
            "fileName": "expotech-2026.jpg",
            "caption": caption,
        }
        files = {"file": ("expotech-2026.jpg", image, "image/jpeg")}

        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(url, data=form, files=files)
        except httpx.HTTPError as exc:
            raise GreenApiError("Não foi possível enviar a foto pela Green API.") from exc

        if not response.is_success:
            raise GreenApiError(
                f"Green API respondeu HTTP {response.status_code} durante o envio."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GreenApiError("Green API retornou uma resposta inválida ao enviar a foto.") from exc

        message_id = payload.get("idMessage") if isinstance(payload, dict) else None
        if not isinstance(message_id, str) or not message_id:
            raise GreenApiError("Green API não confirmou o recebimento da mensagem.")
        return message_id
