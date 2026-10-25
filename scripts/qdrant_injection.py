"""Substitui a base de FAQs no Qdrant, sem acumular respostas antigas."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.knowledge_load import ROOT, ambiente, sincronizar


def main():
    cliente, embeddings = ambiente()
    try:
        caminho = Path(os.getenv("FAQ_FILE_PATH") or ROOT / "scripts/bases/NexUs_FAQs.json")
        if not caminho.is_absolute():
            caminho = ROOT / caminho
        faqs = json.loads(caminho.read_text(encoding="utf-8"))
        documentos = [
            {
                "page_content": f"Pergunta: {f['pergunta']} Resposta: {f['resposta']}",
                "metadata": {"resposta_pura": f["resposta"]},
            }
            for f in faqs
        ]
        sincronizar(documentos, "nexus_faqs", cliente, embeddings)
    finally:
        cliente.close()


if __name__ == "__main__":
    main()
