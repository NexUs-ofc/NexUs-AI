import logging

from langchain.tools import tool

from app.repository.qdrant.faq_repository import FAQRepository

logger = logging.getLogger(__name__)

faq_repo = FAQRepository()

# Mesma regra das tools de estoque: falha de consulta nao pode virar "nao
# existe". O Qdrant devolve ResponseHandlingException quando a leitura estoura
# o tempo, e isso subia da tool para o no, derrubando a requisicao inteira.
FALHA_NA_BUSCA = (
    "FALHA: nao foi possivel consultar a base de conhecimento agora. "
    "Isto NAO significa que a resposta nao existe — avise a pessoa que "
    "a consulta nao funcionou e ofereca tentar de novo."
)


@tool("faq_retriever")
def faq_retriever(question: str) -> str:
    """
    Busca respostas somente na coleção de FAQs do Qdrant.
    """

    alguma_falhou = False

    try:
        respostas_encontradas = faq_repo.buscar_respostas_faq(question)
    except Exception:
        logger.exception("Falha ao consultar a base de FAQs no Qdrant")
        respostas_encontradas = []
        alguma_falhou = True

    respostas_formatadas = [f"- {resp}" for resp in respostas_encontradas]

    # Ausência de resultados é diferente de falha da consulta.
    if alguma_falhou and not respostas_formatadas:
        return FALHA_NA_BUSCA

    return "\n".join(respostas_formatadas)
