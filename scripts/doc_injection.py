"""Substitui a documentação no Qdrant após atualizar o PDF local."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.knowledge_load import ROOT, ambiente, sincronizar


def main():
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    cliente, embeddings = ambiente()
    try:
        caminho = Path(os.getenv("DOC_FILE_PATH") or ROOT / "scripts/bases/NexUs_doc.pdf")
        if not caminho.is_absolute():
            caminho = ROOT / caminho
        chunks = RecursiveCharacterTextSplitter(
            chunk_size=400, chunk_overlap=50,
        ).split_documents(PyPDFLoader(str(caminho)).load())
        documentos = [
            {"page_content": d.page_content, "metadata": d.metadata}
            for d in chunks
        ]
        sincronizar(documentos, "nexus_docs", cliente, embeddings)
    finally:
        cliente.close()


if __name__ == "__main__":
    main()
