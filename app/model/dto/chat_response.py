from pydantic import BaseModel


class ChatResponse(BaseModel):
    resposta: str
    session_id: str | None = None