"""
Dependência de autenticação das rotas.

A estratégia é a mesma da API Core: o token vem do mobile no cabeçalho
Authorization, e a validade é decidida aqui mesmo, pela assinatura — não há
consulta a sessão, a Redis nem ao microsserviço de autenticação.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import VALID_TOKENS
from .api_key_validator import validate_api_key
from .jwt_handler import TokenInvalido, decodificar_token

security = HTTPBearer(auto_error=False)

NAO_AUTORIZADO = {"WWW-Authenticate": "Bearer"}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    api_key: Annotated[str, Depends(validate_api_key)],
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers=NAO_AUTORIZADO,
        )

    token = credentials.credentials

    # Atalho de desenvolvimento: tokens listados em VALID_TOKENS passam sem
    # verificação de assinatura. Em produção a variável fica vazia e este
    # ramo nunca executa.
    if token in VALID_TOKENS:
        return {"user_id": 0, "token": token, "claims": {}, "teste": True}

    try:
        claims = decodificar_token(token)
    except TokenInvalido as erro:
        raise HTTPException(
            status_code=401,
            detail=str(erro),
            headers=NAO_AUTORIZADO,
        ) from erro

    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as erro:
        raise HTTPException(
            status_code=401,
            detail="Token sem identificação de perfil",
            headers=NAO_AUTORIZADO,
        ) from erro

    return {"user_id": user_id, "token": token, "claims": claims, "teste": False}
