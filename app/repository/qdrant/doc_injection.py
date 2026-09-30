# Arquivo de embedding, rodar apenas para subir a documentação técnica para o Qdrant Cloud. Não é necessário rodar em produção.


from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ...config import (
    DOC_FILE_PATH,
    GEMINI_API_KEY,
    QDRANT_API_KEY,
    QDRANT_DATABASE_URL,
)
from .doc_repository import DOCS_COLLECTION

embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2-preview",
    google_api_key=GEMINI_API_KEY,
)

splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)

chunks = splitter.split_documents(PyPDFLoader(DOC_FILE_PATH).load())

print(f"Subindo {len(chunks)} chunks da documentação para o Qdrant Cloud...")

QdrantVectorStore.from_documents(
    chunks,
    embeddings,
    url=QDRANT_DATABASE_URL,
    api_key=QDRANT_API_KEY,
    collection_name=DOCS_COLLECTION,
)

print("Documentação técnica indexada com sucesso na nuvem!")
