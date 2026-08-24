import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


load_dotenv()

_session_factory = None


def _get_session_factory():
    """Cria a fábrica PostgreSQL somente quando uma tool a utilizar."""

    global _session_factory

    if _session_factory is None:
        pgsql_url = os.getenv("PGSQL_URL")
        if not pgsql_url:
            raise RuntimeError(
                "PGSQL_URL não configurada. Defina a variável no ambiente ou no .env."
            )

        engine = create_engine(pgsql_url, echo=False)
        _session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
        )

    return _session_factory


def SessionLocal() -> Session:
    """Abre uma sessão PostgreSQL sob demanda."""

    return _get_session_factory()()