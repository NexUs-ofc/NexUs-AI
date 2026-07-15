import os
import qdrant_client
from dotenv import load_dotenv, find_dotenv
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv(find_dotenv())

class FAQRepository:
    def __init__(self):
        self.url = os.getenv("QDRANT_DATABASE_URL")
        self.api_key = os.getenv("QDRANT_API_KEY")
        self.google_api_key = os.getenv("GEMINI_API_KEY")
        
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
            collection_name="nexus_faqs",
            embedding=self.embeddings,
        )

    def buscar_respostas_faq(self, question: str, limite_corte: float = 0.70) -> list[str]:
        """
        Busca no Qdrant, aplica o filtro de corte e retorna apenas os textos puros.
        """
        resultados_brutos = self.db.similarity_search_with_score(question, k=5)
        

        respostas_validas = [doc for doc, score in resultados_brutos if score > limite_corte][:2]
        

        return [doc.metadata["resposta_pura"].replace("\n", " ").strip() for doc in respostas_validas]