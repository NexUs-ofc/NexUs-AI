import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.config import (
    GROQ_API_KEY,
    LANGCHAIN_API_KEY,
    LANGCHAIN_PROJECT,
    LANGCHAIN_TRACING_V2,
)
from app.controller.config import logging

logger = logging.getLogger(__name__)

INICIADO_EM = datetime.now(timezone.utc)

TIMEOUT_SEGUNDOS = 5


def _medir(nome: str, funcao) -> dict:
    inicio = time.perf_counter()

    try:
        detalhe = funcao()
        return {
            "nome": nome,
            "status": "ok",
            "latencia_ms": round((time.perf_counter() - inicio) * 1000, 1),
            "detalhe": detalhe,
        }
    except Exception as erro:
        logger.exception(f"Healthcheck de {nome} falhou")

        return {
            "nome": nome,
            "status": "erro",
            "latencia_ms": round((time.perf_counter() - inicio) * 1000, 1),
            "detalhe": f"{type(erro).__name__}: {str(erro)[:120]}",
        }


def _checar_mongodb() -> str:
    from pymongo import MongoClient

    from app.config import MONGODB_URI

    cliente = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=TIMEOUT_SEGUNDOS * 1000)
    cliente.admin.command("ping")

    return "conectado"


def _checar_postgres() -> str:
    from sqlalchemy import text

    from app.repository.pgsql.config import SessionLocal

    with SessionLocal() as sessao:
        sessao.execute(text("SELECT 1")).scalar()

    return "conectado"


def _checar_qdrant() -> str:
    from app.repository.qdrant.config import client

    colecoes = client.get_collections().collections

    return f"{len(colecoes)} collections"


def _checar_redis() -> str:
    from app.auth.redis_client import get_redis_client

    get_redis_client().ping()

    return "conectado"


def _checar_tcp(url: str) -> str:
    alvo = urlparse(url if "//" in url else f"//{url}")
    porta = alvo.port or (443 if (alvo.scheme or "https") == "https" else 80)

    conexao = socket.create_connection((alvo.hostname, porta), timeout=TIMEOUT_SEGUNDOS)
    conexao.close()

    return "alcançável"


def _checar_groq() -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada")

    return _checar_tcp("https://api.groq.com")


def _checar_langsmith() -> str:
    tracing_ligado = str(LANGCHAIN_TRACING_V2).lower() in ("true", "1", "yes")

    if not tracing_ligado:
        raise RuntimeError("tracing desligado")

    if not LANGCHAIN_API_KEY:
        raise RuntimeError("LANGCHAIN_API_KEY não configurada")

    _checar_tcp("https://api.smith.langchain.com")

    return f"projeto {LANGCHAIN_PROJECT}"


def _uptime_segundos() -> float:
    return round((datetime.now(timezone.utc) - INICIADO_EM).total_seconds(), 1)


def _recursos() -> dict:
    """
    Consumo do processo da API: memória residente e CPU.
    """

    import psutil

    processo = psutil.Process()
    memoria = processo.memory_info()
    virtual = psutil.virtual_memory()

    return {
        "memoria_mb": round(memoria.rss / (1024 * 1024), 1),
        "memoria_pct": round(processo.memory_percent(), 2),
        "cpu_pct": round(processo.cpu_percent(interval=None), 1),
        "cpu_sistema_pct": round(psutil.cpu_percent(interval=None), 1),
        "memoria_sistema_disponivel_mb": round(virtual.available / (1024 * 1024), 1),
        "threads": processo.num_threads(),
    }


def checar_saude() -> dict:
    """
    Estado das dependências externas da API.

    Não calcula latência de agente, custo nem taxa de erro: essas métricas
    vivem no LangSmith e nos relatórios.
    """

    checagens = [
        _medir("MongoDB", _checar_mongodb),
        _medir("PostgreSQL", _checar_postgres),
        _medir("Qdrant", _checar_qdrant),
        _medir("Redis", _checar_redis),
        _medir("Groq", _checar_groq),
        _medir("LangSmith", _checar_langsmith),
    ]

    com_erro = [c for c in checagens if c["status"] == "erro"]

    if not com_erro:
        estado = "saudavel"
    elif len(com_erro) == len(checagens):
        estado = "indisponivel"
    else:
        estado = "degradado"

    return {
        "estado": estado,
        "verificado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "uptime_segundos": _uptime_segundos(),
        "recursos": _recursos(),
        "dependencias": checagens,
        "falhas": len(com_erro),
        "total": len(checagens),
    }


def checar_vivo() -> dict:
    """
    Liveness: só confirma que o processo responde, sem tocar em dependência.
    """

    return {
        "estado": "vivo",
        "uptime_segundos": _uptime_segundos(),
        "verificado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
