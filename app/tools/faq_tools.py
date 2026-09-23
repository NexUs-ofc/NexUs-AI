from langchain.tools import tool

from app.repository.qdrant.doc_repository import DocRepository
from app.repository.qdrant.faq_repository import FAQRepository

faq_repo = FAQRepository()
doc_repo = DocRepository()

@tool("faq_retriever")
def faq_retriever(question: str) -> str:
    """
    Busca respostas no banco de conhecimento do NexUs.
    Prioriza a base de FAQs (Qdrant). Se encontrar menos de 2 respostas
    relevantes, completa a busca utilizando a documentação técnica (PDF).
    """

    respostas_encontradas = faq_repo.buscar_respostas_faq(question)

    respostas_formatadas = [f"- {resp}" for resp in respostas_encontradas]

    vagas_restantes = 2 - len(respostas_formatadas)

    if vagas_restantes > 0:
        trechos = doc_repo.buscar_trechos_documentacao(question, k=vagas_restantes)

        for trecho in trechos:
            respostas_formatadas.append(f"- {trecho}")

    return "\n".join(respostas_formatadas)
