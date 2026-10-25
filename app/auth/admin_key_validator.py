import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from ..config import ADMIN_API_KEY

ADMIN_KEY_HEADER = "X-Admin-Key"

_admin_key_header = APIKeyHeader(
    name=ADMIN_KEY_HEADER,
    scheme_name="AdminApiKey",
    description="Chave do painel do administrador.",
    auto_error=False,
)


def validate_admin_key(api_key: str = Security(_admin_key_header)) -> str:
    """
    Chave do painel do administrador, a mesma em todos os serviços do NexUs.

    Não aceita a API key do aplicativo nem o JWT do usuário: o painel e o
    mobile têm credenciais separadas de propósito.
    """

    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Chave do painel não configurada no servidor (ADMIN_API_KEY).",
        )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Admin key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not secrets.compare_digest(api_key.strip().encode(), ADMIN_API_KEY.strip().encode()):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
