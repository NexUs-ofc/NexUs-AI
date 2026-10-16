# Arquivo de embedding, rodar apenas para subir os dados para o Qdrant Cloud. Não é necessário rodar em produção.


import json
import os
import time

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

load_dotenv()


faq_file = os.getenv("FAQ_FILE_PATH")
url = os.getenv("QDRANT_DATABASE_URL")
api_key = os.getenv("QDRANT_API_KEY")

COLECAO = "nexus_faqs"
TAMANHO_LOTE = 20
PAUSA_S = 65


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

print(f"Subindo {len(docs)} FAQs para o Qdrant Cloud em lotes de {TAMANHO_LOTE}...")


store = QdrantVectorStore.from_documents(
    docs[:TAMANHO_LOTE],
    embeddings,
    url=url,
    api_key=api_key,
    collection_name=COLECAO,
)
print(f"  {min(TAMANHO_LOTE, len(docs))}/{len(docs)}")

for inicio in range(TAMANHO_LOTE, len(docs), TAMANHO_LOTE):
    time.sleep(PAUSA_S)
    lote = docs[inicio:inicio + TAMANHO_LOTE]
    store.add_documents(lote)
    print(f"  {min(inicio + TAMANHO_LOTE, len(docs))}/{len(docs)}")

print("Banco vetorial atualizado na nuvem!")
