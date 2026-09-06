from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from ..config import API_KEY_HEADER

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def validate_api_key(api_key: str = Security(_api_key_header)) -> str:
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if len(api_key) < 32:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format",
        )
    return api_key
