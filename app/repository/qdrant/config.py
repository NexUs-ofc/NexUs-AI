from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient

from ...config import GEMINI_API_KEY, QDRANT_API_KEY, QDRANT_DATABASE_URL

SESSION_SUMMARY_COLLECTION = "session_summary"
PROFILE_PREFERENCES_COLLECTION = "profile_preferencies"

EMBEDDING_DIM = 768

# port=None faz o cliente respeitar a porta implicita do https (443). Sem isso
# ele assume 6333, que varias redes bloqueiam — e como esta conexao acontece no
# import, a aplicacao inteira deixa de subir, nao so a busca vetorial.
client = QdrantClient(
    url=QDRANT_DATABASE_URL,
    api_key=QDRANT_API_KEY,
    port=None,
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
