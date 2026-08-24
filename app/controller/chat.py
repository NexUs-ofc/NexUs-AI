from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.flow import executar_chat

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    resultado = executar_chat(
        mensagem=request.mensagem,
        session_id=request.session_id,
        household_account_id=request.household_account_id,
        account_id=request.account_id,
    )

    return ChatResponse(**resultado)