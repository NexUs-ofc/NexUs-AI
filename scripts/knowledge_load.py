"""Recarga reconciliada das coleções dedicadas de conhecimento do Ceris."""

import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sincronizar(documentos, colecao, cliente, embeddings, lote=20, pausa=65):
    """Publica toda a base antes de remover pontos da versão anterior.

    IDs estáveis evitam duplicatas. Falhas de embedding ou upload preservam
    os documentos antigos. Nunca usar em memória ou preferências de usuários.
    """
    from qdrant_client import models

    if not documentos:
        raise ValueError("Base vazia: recarga cancelada sem excluir documentos.")
    if lote < 1 or pausa < 0:
        raise ValueError("Lote deve ser positivo e pausa não pode ser negativa.")
    if colecao not in {"nexus_faqs", "nexus_docs"}:
        raise ValueError("A recarga só atende às coleções de conhecimento.")
    ids = [
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"ceris:{colecao}:{d['page_content']}"))
        for d in documentos
    ]
    if len(set(ids)) != len(ids):
        raise ValueError("Base contém documentos duplicados.")

    existe = cliente.collection_exists(colecao)
    antigos = set()
    if existe:
        offset = None
        while True:
            pontos, offset = cliente.scroll(
                collection_name=colecao, offset=offset, limit=256,
                with_payload=False, with_vectors=False,
            )
            antigos.update(str(p.id) for p in pontos)
            if offset is None:
                break

    print(f"Publicando {len(documentos)} documentos em {colecao}...", flush=True)
    for inicio in range(0, len(documentos), lote):
        if inicio:
            time.sleep(pausa)
        recorte = documentos[inicio:inicio + lote]
        vetores = embeddings.embed_documents([d["page_content"] for d in recorte])
        if len(vetores) != len(recorte) or not vetores or not vetores[0]:
            raise ValueError("Embedding incompleto: documentos antigos preservados.")
        dimensao = len(vetores[0])
        if any(len(v) != dimensao for v in vetores):
            raise ValueError("Dimensões de embedding inconsistentes.")
        if not existe:
            cliente.create_collection(
                collection_name=colecao,
                vectors_config=models.VectorParams(size=dimensao, distance=models.Distance.COSINE),
            )
            existe = True
        cliente.upsert(
            collection_name=colecao, wait=True,
            points=[
                models.PointStruct(id=ids[inicio + i], vector=v, payload=d)
                for i, (d, v) in enumerate(zip(recorte, vetores, strict=True))
            ],
        )
        print(f"  {min(inicio + lote, len(documentos))}/{len(documentos)}", flush=True)

    obsoletos = sorted(antigos - set(ids))
    for inicio in range(0, len(obsoletos), 256):
        cliente.delete(
            collection_name=colecao, wait=True,
            points_selector=models.PointIdsList(points=obsoletos[inicio:inicio + 256]),
        )
    encontrados = cliente.count(collection_name=colecao, exact=True).count
    if encontrados != len(documentos):
        raise RuntimeError(f"Contagem divergente: esperado {len(documentos)}, encontrado {encontrados}.")
    print(f"{colecao}: {encontrados} documentos; {len(obsoletos)} obsoletos removidos.", flush=True)
    return ids


def ambiente():
    import os

    from dotenv import load_dotenv
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from qdrant_client import QdrantClient

    load_dotenv(ROOT / ".env")
    faltando = [
        nome for nome in ("QDRANT_DATABASE_URL", "QDRANT_API_KEY", "GEMINI_API_KEY")
        if not os.getenv(nome)
    ]
    if faltando:
        raise RuntimeError("Configuração ausente: " + ", ".join(faltando))
    cliente = QdrantClient(
        url=os.environ["QDRANT_DATABASE_URL"], api_key=os.environ["QDRANT_API_KEY"],
        port=None, timeout=60,
    )
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2-preview", google_api_key=os.environ["GEMINI_API_KEY"],
    )
    return cliente, embeddings
