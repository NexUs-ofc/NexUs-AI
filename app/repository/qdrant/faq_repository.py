import qdrant_client
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from ...config import GEMINI_API_KEY, QDRANT_API_KEY, QDRANT_DATABASE_URL
from .config import TEMPO_LIMITE_BUSCA_S


class FAQRepository:
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
            port=None,
            timeout=TEMPO_LIMITE_BUSCA_S,
            # Sem checagem de versao: e uma chamada de rede no import.
            check_compatibility=False,
        )

        self._db = None

    @property
    def db(self) -> QdrantVectorStore:
        # O QdrantVectorStore valida a collection no servidor ao ser criado.
        # Feito no import, um Qdrant fora de alcance impedia a API de subir;
        # aqui so acontece na primeira busca, que ja trata a falha.
        if self._db is None:
            self._db = QdrantVectorStore(
                client=self.client,
                collection_name="nexus_faqs",
                embedding=self.embeddings,
            )

        return self._db

    def buscar_respostas_faq(self, question: str, limite_corte: float = 0.70) -> list[str]:
        """
        Busca no Qdrant, aplica o filtro de corte e retorna apenas os textos puros.
        """
        resultados_brutos = self.db.similarity_search_with_score(question, k=5)

        respostas_validas = [doc for doc, score in resultados_brutos if score > limite_corte][:2]

        return [doc.metadata["resposta_pura"].replace("\n", " ").strip() for doc in respostas_validas]