import qdrant_client
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from ...config import GEMINI_API_KEY, QDRANT_API_KEY, QDRANT_DATABASE_URL

DOCS_COLLECTION = "nexus_docs"


class DocRepository:
    def __init__(self):
        self.url = QDRANT_DATABASE_URL
        self.api_key = QDRANT_API_KEY
        self.google_api_key = GEMINI_API_KEY

        if not self.url:
            raise ValueError("QDRANT_DATABASE_URL não foi encontrada. O arquivo .env não foi lido corretamente.")

        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-2-preview",
            google_api_key=self.google_api_key,
        )

        self.client = qdrant_client.QdrantClient(
            url=self.url,
            api_key=self.api_key,
        )

        self.db = QdrantVectorStore(
            client=self.client,
            collection_name=DOCS_COLLECTION,
            embedding=self.embeddings,
        )

    def buscar_trechos_documentacao(self, question: str, k: int = 2) -> list[str]:
        """
        Busca trechos da documentação técnica já indexada no Qdrant.

        Substitui a reconstrução do índice FAISS a cada chamada: o PDF é
        processado uma única vez, pelo doc_injection.
        """

        if k <= 0:
            return []

        resultados = self.db.similarity_search(question, k=k)

        return [doc.page_content.replace("\n", " ").strip() for doc in resultados]
