from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    resposta: str
    session_id: str | None = None
    respostas_recomendadas: list[str] | None = Field(default=None, max_length=3)
