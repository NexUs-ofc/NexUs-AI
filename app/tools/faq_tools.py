import logging

from langchain.tools import tool

from app.repository.qdrant.doc_repository import DocRepository
from app.repository.qdrant.faq_repository import FAQRepository

logger = logging.getLogger(__name__)

faq_repo = FAQRepository()
doc_repo = DocRepository()

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
    Busca respostas no banco de conhecimento do NexUs.
    Prioriza a base de FAQs (Qdrant). Se encontrar menos de 2 respostas
    relevantes, completa a busca utilizando a documentação técnica (PDF).
    """

    alguma_falhou = False

    try:
        respostas_encontradas = faq_repo.buscar_respostas_faq(question)
    except Exception:
        logger.exception("Falha ao consultar a base de FAQs no Qdrant")
        respostas_encontradas = []
        alguma_falhou = True

    respostas_formatadas = [f"- {resp}" for resp in respostas_encontradas]

    vagas_restantes = 2 - len(respostas_formatadas)

    if vagas_restantes > 0:
        try:
            trechos = doc_repo.buscar_trechos_documentacao(question, k=vagas_restantes)
        except Exception:
            logger.exception("Falha ao consultar a documentacao no Qdrant")
            trechos = []
            alguma_falhou = True

        for trecho in trechos:
            respostas_formatadas.append(f"- {trecho}")

    # Vazio por nao achar nada e vazio por ter quebrado sao coisas diferentes:
    # so o segundo vira aviso. Se uma das duas buscas respondeu, o que veio
    # vale mais do que o alarme.
    if alguma_falhou and not respostas_formatadas:
        return FALHA_NA_BUSCA

    return "\n".join(respostas_formatadas)
