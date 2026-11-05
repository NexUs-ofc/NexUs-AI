"""Autorização dedicada para o tablet/telefone fixo do estande."""

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def require_photobooth_key(
    key: Annotated[str | None, Header(alias="X-PhotoBooth-Key")] = None,
) -> str:
    configured = [
        value.strip()
        for value in os.getenv("PHOTOBOOTH_API_KEY", "").split(",")
        if value.strip()
    ]
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="A chave da cabine PhotoBooth não está configurada na API.",
        )
    if not key or not any(hmac.compare_digest(key, candidate) for candidate in configured):
        raise HTTPException(
            status_code=401,
            detail="Chave da cabine inválida.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return key
