"""Rotas da cabine de fotos Expotech."""

import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth.photobooth import require_photobooth_key
from app.services.greenapi_client import (
    GreenApiClient,
    GreenApiError,
    GreenApiNotConfigured,
    GreenApiNotReady,
)

router = APIRouter(prefix="/photobooth", tags=["PhotoBooth"])
MAX_UPLOAD_MB = max(1, min(int(os.getenv("PHOTOBOOTH_MAX_UPLOAD_MB", "10")), 20))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
JPEG_SIGNATURE = b"\xff\xd8\xff"


def _normalizar_telefone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) in (10, 11):
        return f"55{digits}"
    if 12 <= len(digits) <= 15 and not digits.startswith("0"):
        return digits
    raise HTTPException(
        status_code=422,
        detail="Informe um telefone com DDD e código do país.",
    )


async def _ler_foto(photo: UploadFile) -> bytes:
    if photo.content_type != "image/jpeg":
        raise HTTPException(status_code=415, detail="Envie a foto final em formato JPEG.")
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="A foto está vazia.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"A foto excede o limite de {MAX_UPLOAD_MB} MB.",
        )
    if not data.startswith(JPEG_SIGNATURE):
        raise HTTPException(status_code=415, detail="O arquivo enviado não é um JPEG válido.")
    return data


@router.get("/status")
async def status(_key: str = Depends(require_photobooth_key)) -> dict:
    """Estado seguro da instância, sem retornar URLs ou credenciais."""
    try:
        state = await GreenApiClient().get_instance_state()
    except GreenApiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GreenApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"stateInstance": state, "ready": state == "authorized"}


@router.post("/send", status_code=202)
async def send_photo(
    name: str = Form(..., min_length=2, max_length=80),
    phone: str = Form(..., min_length=10, max_length=18),
    consent: bool = Form(...),
    photo: UploadFile = File(...),  # noqa: B008
    _key: str = Depends(require_photobooth_key),
) -> dict:
    """Envia a foto composta como imagem e a mensagem como legenda do WhatsApp."""
    name = " ".join(name.split())
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Informe seu nome.")
    if not consent:
        raise HTTPException(status_code=403, detail="É necessário autorizar o envio da foto.")

    phone_digits = _normalizar_telefone(phone)
    image = await _ler_foto(photo)

    try:
        message_id = await GreenApiClient().send_photo(
            phone=phone_digits,
            name=name,
            image=image,
        )
    except GreenApiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GreenApiNotReady as exc:
        raise HTTPException(
            status_code=503,
            detail="A conta WhatsApp do estande não está conectada à Green API.",
        ) from exc
    except GreenApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Green API confirma que colocou a mídia na fila; a entrega no WhatsApp
    # pode acontecer alguns segundos depois.
    return {"status": "queued", "idMessage": message_id}

