from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient

from ...config import GEMINI_API_KEY, QDRANT_API_KEY, QDRANT_DATABASE_URL

SESSION_SUMMARY_COLLECTION = "session_summary"
PROFILE_PREFERENCES_COLLECTION = "profile_preferencies"

EMBEDDING_DIM = 768

# O padrao do QdrantClient e 5s. A busca medida leva de 0,2s a 0,4s, mas um
# pico ocasional passa disso e volta como ResponseHandlingException("The read
# operation timed out") no meio da pergunta. Vale para as buscas de FAQ e
# documentacao, onde o resultado e a resposta; memoria e preferencias ficam no
# padrao de proposito, porque ali a falha so degrada e esperar mais atrasaria
# a pessoa a toa.
TEMPO_LIMITE_BUSCA_S = 15

# port=None faz o cliente respeitar a porta implicita do https (443). Sem isso
# ele assume 6333, que varias redes bloqueiam — e como esta conexao acontece no
# import, a aplicacao inteira deixa de subir, nao so a busca vetorial.
client = QdrantClient(
    url=QDRANT_DATABASE_URL,
    api_key=QDRANT_API_KEY,
    port=None,
    # Sem checagem de versao: e uma chamada de rede no import e, com o Qdrant
    # fora de alcance, segura a subida da API ate o timeout.
    check_compatibility=False,
)

embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2-preview",
    google_api_key=GEMINI_API_KEY,
)


def gerar_embedding(texto: str) -> list[float]:
    """
    Gera um vetor de 768 dimensões, compatível com as collections de memória.
    """

    return embeddings.embed_query(
        texto,
        output_dimensionality=EMBEDDING_DIM,
    )


def gerar_embeddings_lote(textos: list[str]) -> list[list[float]]:
    """
    Gera embeddings de 768 dimensões para vários textos de uma vez.
    """

    return embeddings.embed_documents(
        textos,
        output_dimensionality=EMBEDDING_DIM,
    )
