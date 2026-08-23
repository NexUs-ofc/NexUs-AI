from app.schemas.flow import executar_chat
from fastapi import APIRouter
from ..model.dto.chat_request import ChatRequest
from ..model.dto.chat_response import ChatResponse

router = APIRouter(prefix="/chat")

@router.post("/", response_model=ChatResponse)
def send_message(request: ChatRequest):
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