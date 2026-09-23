from langchain_core.messages import HumanMessage

from app.controller.config import logging
from app.core.llms import fast_llm
from app.core.prompts.prompt_preferencias import PREFERENCIAS_PROMPT
from app.repository.mongodb.activity import ActivityRepository
from app.repository.qdrant.preferences_repository import PreferencesRepository

logger = logging.getLogger(__name__)

MAX_PREFERENCIAS = 8
MAX_MENSAGENS_POR_CONVERSA = 12


def _montar_atividade(account_id: int, household_id: int) -> str:
    blocos = []

    fatos = ActivityRepository.get_knowledge(household_id)

    if fatos:
        linhas = []

        for fato in fatos:
            texto = fato.get("fact", "")
            guia = fato.get("ai_guideline") or {}
            acao = guia.get("recommended_action", "")
            linhas.append(f"- {texto}" + (f" (orientação: {acao})" if acao else ""))

        blocos.append("FATOS JÁ CONHECIDOS:\n" + "\n".join(linhas))

    conversas = ActivityRepository.get_conversas_recentes(account_id)

    if conversas:
        partes = []

        for indice, historico in enumerate(conversas, start=1):
            recorte = historico[-MAX_MENSAGENS_POR_CONVERSA:]
            corpo = "\n".join(
                f"  {m.get('role', '')}: {m.get('content', '')}" for m in recorte
            )
            partes.append(f"Conversa {indice}:\n{corpo}")

        blocos.append("CONVERSAS RECENTES:\n" + "\n".join(partes))

    receitas = ActivityRepository.get_receitas_recentes(account_id)

    if receitas:
        linhas = [
            f"- {r.get('title', '')} "
            f"(curtida: {'sim' if r.get('is_liked') else 'não'}, "
            f"porções: {r.get('serving_size', '?')})"
            for r in receitas
        ]
        blocos.append("RECEITAS SALVAS:\n" + "\n".join(linhas))

    eventos = ActivityRepository.get_eventos_recentes(household_id)

    if eventos:
        linhas = [
            f"- {e.get('title', '')}: {e.get('description', '')} "
            f"({e.get('qtd_people', '?')} pessoas)"
            for e in eventos
        ]
        blocos.append("EVENTOS RECENTES:\n" + "\n".join(linhas))

    registros = ActivityRepository.get_registros_recentes(account_id)

    if registros:
        linhas = [
            f"- {r.get('event_type', '')}: {r.get('details', '')}"
            for r in registros
        ]
        blocos.append("REGISTROS DE USO:\n" + "\n".join(linhas))

    return "\n\n".join(blocos)


def _extrair_linhas(resposta: str) -> list[str]:
    if resposta.strip().upper().startswith("NENHUMA"):
        return []

    preferencias = []

    for linha in resposta.splitlines():
        texto = linha.strip()

        if not texto.startswith("- "):
            continue

        texto = texto[2:].strip()

        if texto:
            preferencias.append(texto)

    return preferencias[:MAX_PREFERENCIAS]


def derivar_preferencias(account_id: int, household_id: int) -> list[str]:
    """
    Resume a atividade recente do usuário no MongoDB em preferências
    permanentes e grava cada uma na collection de preferências do Qdrant.

    Devolve as preferências derivadas, para validação.
    """

    atividade = _montar_atividade(account_id, household_id)

    if not atividade.strip():
        logger.info(f"Conta {account_id} não tem atividade para derivar preferências")
        return []

    try:
        resposta = fast_llm.invoke([
            HumanMessage(
                content=PREFERENCIAS_PROMPT.format(atividade=atividade)
            )
        ])
    except Exception:
        logger.exception(f"Erro ao derivar preferências da conta {account_id}")
        raise

    preferencias = _extrair_linhas(resposta.content)

    if not preferencias:
        logger.info(f"Nenhuma preferência extraída para a conta {account_id}")
        return []

    for preferencia in preferencias:
        PreferencesRepository.salvar_preferencia(account_id, preferencia)

    logger.info(
        f"Conta {account_id} teve {len(preferencias)} preferências derivadas"
    )

    return preferencias
