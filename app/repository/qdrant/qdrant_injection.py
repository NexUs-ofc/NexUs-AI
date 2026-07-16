# Arquivo de embedding, rodar apenas para subir os dados para o Qdrant Cloud. Não é necessário rodar em produção.


import os
import json
from dotenv import load_dotenv
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

load_dotenv()


faq_file = os.getenv("FAQ_FILE_PATH")
url = os.getenv("QDRANT_DATABASE_URL")
api_key = os.getenv("QDRANT_API_KEY")


embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2-preview",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)


with open(faq_file, "r", encoding="utf-8") as f:
    faqs = json.load(f)

docs = []
for item in faqs:
    conteudo_busca = f"Pergunta: {item['pergunta']} Resposta: {item['resposta']}"
    docs.append(Document(
        page_content=conteudo_busca, 
        metadata={"resposta_pura": item['resposta']}
    ))

print("Subindo dados para o Qdrant Cloud...")


QdrantVectorStore.from_documents(
    docs,
    embeddings,
    url=url,
    api_key=api_key,
    collection_name="nexus_faqs"
)

print("Banco vetorial criado com sucesso na nuvem!")