from pydantic import BaseModel

class ChatRequest(BaseModel):
    mensagem: str
    session_id: str | None = None
    household_account_id: int = 1
    account_id: int = 1

class ChatResponse(BaseModel):
    resposta: str
    session_id: str