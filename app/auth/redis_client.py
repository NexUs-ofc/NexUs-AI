import redis
from ..config import REDIS_URL

_redis_client = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def set_session(session_id: str, user_data: dict, expiration_seconds: int) -> None:
    client = get_redis_client()
    client.setex(f"session:{session_id}", expiration_seconds, str(user_data))


def get_session(session_id: str) -> dict | None:
    client = get_redis_client()
    session_data = client.get(f"session:{session_id}")
    if session_data:
        return eval(session_data)
    return None


def delete_session(session_id: str) -> None:
    client = get_redis_client()
    client.delete(f"session:{session_id}")


def invalidate_user_sessions(user_id: str) -> None:
    client = get_redis_client()
    pattern = f"session:*"
    keys = client.keys(pattern)
    for key in keys:
        session_data = client.get(key)
        if session_data and str(user_id) in session_data:
            client.delete(key)
