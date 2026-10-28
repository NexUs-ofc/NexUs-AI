from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langsmith import Client
from pydantic import BaseModel, Field

from app.controller.config import logging
from app.schemas.flow import executar_chat
from app.schemas.memory import encerrar_sessao

from ..auth.dependencies import get_current_user
from ..model.dto.chat_request import ChatRequest
from ..model.dto.chat_response import ChatResponse
from ..repository.mongodb.conversations import ConversationsRepository

router = APIRouter(prefix="/chat")
logger = logging.getLogger(__name__)


class SectionFeedback(BaseModel):
    nota: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=2000)


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
    avaliacao: SectionFeedback | None = None,
):
    account_id = user["user_id"]

    if not ConversationsRepository.pertence_conta(session_id, account_id):
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")

    # Persist the closed state first. Summary generation or LangSmith outages
    # must never leave a conversation open after the user requested closure.
    ja_encerrada = ConversationsRepository.sessao_encerrada(session_id, account_id)
    encerrada = ja_encerrada or ConversationsRepository.end_session(session_id, account_id)
    memoria = {"resumo": "", "preferencias": []}
    if encerrada and not ja_encerrada:
        try:
            memoria = encerrar_sessao(
                session_id=session_id,
                account_id=account_id,
                household_id=_casa_do_token(user, household_account_id) or account_id,
            )
        except Exception:
            logger.exception("Falha ao finalizar memória da sessão já fechada")

    resultado_feedback = "nao_enviada"
    if avaliacao is not None:
        estado, trace_id = ConversationsRepository.submit_section_feedback(
            session_id, account_id, avaliacao.nota, avaliacao.feedback,
        )
        if estado == "claimed" and trace_id:
            try:
                Client().create_feedback(
                    run_id=trace_id,
                    key="avaliacao_secao",
                    score=avaliacao.nota,
                    comment=avaliacao.feedback,
                )
                ConversationsRepository.update_section_feedback_status(
                    session_id, account_id, "sent",
                )
                resultado_feedback = "registrada"
            except Exception:
                logger.exception("Não foi possível registrar a avaliação no LangSmith")
                ConversationsRepository.update_section_feedback_status(
                    session_id, account_id, "failed",
                )
                resultado_feedback = "falha_no_registro"
        elif estado == "duplicate":
            resultado_feedback = "ja_registrada"
        else:
            resultado_feedback = estado

    return {
        "session_id": session_id,
        "encerrada": encerrada,
        "resumo": memoria["resumo"] or None,
        "preferencias": memoria["preferencias"],
        "avaliacao": resultado_feedback,
    }
