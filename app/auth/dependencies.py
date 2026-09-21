from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .api_key_validator import validate_api_key
from .jwt_handler import get_user_id_from_token
from .session_validator import validate_session

security = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    api_key: Annotated[str, Depends(validate_api_key)],
) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    session_id = request.path_params.get("session_id") or request.query_params.get("session_id")
    if session_id:
        validate_session(session_id, token)

    return {"user_id": user_id, "token": token}
