import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from ..config import TRACING_API_KEY

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_api_key(api_key: str = Security(_api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not TRACING_API_KEY or not secrets.compare_digest(api_key, TRACING_API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
