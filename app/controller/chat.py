from pydantic import BaseModel
from .config import app
from app.schemas.flow import executar_chat

class ChatRequest(BaseModel):
    mensagem: str
    session_id: str | None = None
    household_account_id: int = 1
    account_id: int = 1

class ChatResponse(BaseModel):
    resposta: str
    session_id: str

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    resultado = executar_chat(
        mensagem=request.mensagem,
        session_id=request.session_id,
        household_account_id=request.household_account_id,
        account_id=request.account_id,
    )

    return ChatResponse(
        resposta=resultado["resposta"],
        session_id=resultado["session_id"],
    )