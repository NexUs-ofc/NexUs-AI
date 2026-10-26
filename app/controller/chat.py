from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.flow import executar_chat
from app.schemas.memory import encerrar_sessao

from ..auth.dependencies import get_current_user
from ..model.dto.chat_request import ChatRequest
from ..model.dto.chat_response import ChatResponse
from ..repository.mongodb.conversations import ConversationsRepository

router = APIRouter(prefix="/chat")

def _casa_do_token(user: dict, informada: int | None) -> int | None:
    """
    A casa dona do estoque sai do token, como na Core.

    Vinha do corpo do pedido com default 1: o app nao mandava o campo e tudo
    que a Cerita gravava caia no perfil 1, invisivel para a pessoa. E qualquer
    cliente podia mandar o id de outra casa e ler ou mexer no estoque dela.

    O valor informado so vale para os tokens de desenvolvimento, que chegam
    com user_id 0 e nao tem casa de verdade.
    """

    casa = user["user_id"] or informada

    if not casa:
        raise HTTPException(
            status_code=422,
            detail="household_account_id e obrigatorio com token de desenvolvimento.",
        )

    return casa


@router.post("/", response_model=ChatResponse)
def send_message(request: ChatRequest, user: Annotated[dict, Depends(get_current_user)]):
    resultado = executar_chat(
        mensagem=request.mensagem,
        session_id=request.session_id,
        household_account_id=_casa_do_token(user, request.household_account_id),
        account_id=user["user_id"],
    )

    return ChatResponse(
        resposta=resultado["resposta"],
        session_id=resultado["session_id"],
    )


@router.delete("/{session_id}")
def end_session(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    household_account_id: int | None = None,
):
    account_id = user["user_id"]

    if not ConversationsRepository.pertence_conta(session_id, account_id):
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")

    memoria = encerrar_sessao(
        session_id=session_id,
        account_id=account_id,
        household_id=_casa_do_token(user, household_account_id) or account_id,
    )

    encerrada = ConversationsRepository.end_session(session_id, account_id)

    return {
        "session_id": session_id,
        "encerrada": encerrada,
        "resumo": memoria["resumo"] or None,
        "preferencias": memoria["preferencias"],
    }