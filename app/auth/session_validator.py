from fastapi import HTTPException, Depends
from .redis_client import get_session, delete_session
from .jwt_handler import get_user_id_from_token


def validate_session(session_id: str, token: str) -> dict:
    session_data = get_session(session_id)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid",
        )

    user_id_from_token = get_user_id_from_token(token)
    if not user_id_from_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    if session_data.get("user_id") != user_id_from_token:
        raise HTTPException(
            status_code=403,
            detail="Session does not belong to this user",
        )

    return session_data


def create_session_for_user(user_id: int, session_id: str, expiration_seconds: int = 1800) -> None:
    from .redis_client import set_session
    session_data = {"user_id": user_id, "created_at": str(user_id)}
    set_session(session_id, session_data, expiration_seconds)


def end_user_session(session_id: str) -> None:
    delete_session(session_id)
