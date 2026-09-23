from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from app.controller.config import logging
from app.core.llms import fast_llm
from app.core.prompts.prompt_resumo import RESUMO_PROMPT
from app.repository.mongodb.conversations import ConversationsRepository
from app.repository.qdrant.memory_repository import MemoryRepository

logger = logging.getLogger(__name__)

MINIMO_MENSAGENS_PARA_RESUMIR = 2


def _formatar_conversa(historico: list[dict]) -> str:
    return "\n".join(
        f"{msg.get('role', '')}: {msg.get('content', '')}"
        for msg in historico
    )


def _gerar_resumo(historico: list[dict]) -> str:
    resposta = fast_llm.invoke([
        HumanMessage(
            content=RESUMO_PROMPT.format(
                conversa=_formatar_conversa(historico)
            )
        )
    ])

    return resposta.content.strip()


def resumir_sessao(session_id: str, account_id: int) -> str:
    """
    Gera o resumo de uma sessão encerrada e grava na memória de longo prazo.

    Devolve o resumo gerado, ou string vazia quando não havia conversa
    suficiente para resumir.
    """

    historico = ConversationsRepository.get_historico(session_id)

    if len(historico) < MINIMO_MENSAGENS_PARA_RESUMIR:
        logger.info(
            f"Sessão {session_id} tem {len(historico)} mensagens, "
            f"insuficiente para resumir"
        )
        return ""

    try:
        resumo = _gerar_resumo(historico)
    except Exception:
        logger.exception(f"Erro ao gerar resumo da sessão {session_id}")
        return ""

    if not resumo:
        return ""

    MemoryRepository.salvar_resumo(
        session_id=session_id,
        account_id=account_id,
        resumo=resumo,
        created_at=datetime.now(timezone.utc),
    )

    return resumo
