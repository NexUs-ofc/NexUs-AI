import os
from dotenv import load_dotenv, find_dotenv
from langchain.tools import tool
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS 
from app.repository.qdrant.faq_repository import FAQRepository

load_dotenv(find_dotenv())
doc_file = os.getenv("DOC_FILE_PATH")

#
faq_repo = FAQRepository()

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
        embeddings = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-2-preview",
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        splitter_pdf = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
        pdf_loader = PyPDFLoader(doc_file)
        pdf_chunks = splitter_pdf.split_documents(pdf_loader.load())
        pdf_db = FAISS.from_documents(pdf_chunks, embeddings)
        
        resultados_pdf = pdf_db.similarity_search(question, k=vagas_restantes)
        
        for doc in resultados_pdf:
            texto_limpo = doc.page_content.replace("\n", " ").strip()
            respostas_formatadas.append(f"- {texto_limpo}")

    return "\n".join(respostas_formatadas)

print(faq_retriever.invoke({"question": "Qual é o email de suporte do NexUs?"}))