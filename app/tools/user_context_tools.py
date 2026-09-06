import json
from langchain.tools import tool

from ..repository.mongodb.conversations import ConversationsRepository
from ..repository.mongodb.knowledge import KnowledgeRepository


@tool("get_user_history")
def get_user_history(
    account_id: int,
    limite: int = 10,
) -> str:
    """
    Busca o histórico geral do usuário, retornando as sessões de conversa já
    ocorridas, ordenadas da mais recente para a mais antiga. Fornece contexto
    sobre o que já foi tratado com o usuário ao longo do tempo.

    Parâmetros:
        - account_id: Identificador da conta do usuário.
        - limite: Quantidade máxima de sessões a retornar (padrão 10).
    """

    sessions = ConversationsRepository.get_user_sessions(
        account_id=account_id,
        limite=limite,
    )

    if not sessions:
        return "Nenhum registro de histórico encontrado para este usuário."

    return json.dumps(
        sessions,
        ensure_ascii=False,
        default=str,
    )


@tool("get_user_profile")
def get_user_profile(
    account_id: int,
    household_id: int = None,
) -> str:
    """
    Busca e retorna o perfil geral do usuário: dados consolidados de identidade
    e preferências, independentes de eventos pontuais. Fornece contexto sobre
    quem é o usuário.

    Parâmetros:
        - account_id: Identificador da conta do usuário.
        - household_id: Identificador da conta/casa (opcional).
    """

    knowledge = KnowledgeRepository.get_knowledge(
        account_id=account_id,
        household_id=household_id,
    )

    if knowledge is None:
        return "Nenhum perfil consolidado encontrado para este usuário."

    return json.dumps(
        knowledge.to_dict(),
        ensure_ascii=False,
        default=str,
    )