from datetime import datetime
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class TracesRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    traces_collection = db.get_collection("traces")

    @staticmethod
    def save_span(
        trace_id: str,
        span_name: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: float,
        extra: dict | None = None,
    ) -> bool:
        try:
            logger.info(f"Salvando span {span_name} ({trace_id})")

            TracesRepository.traces_collection.insert_one({
                "trace_id": trace_id,
                "span_name": span_name,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "extra": extra or {},
            })

            logger.info(f"Span {span_name} ({trace_id}) salvo com sucesso")

            return True

        except PyMongoError:
            logger.exception(f"Erro ao salvar span {span_name} ({trace_id})")
            return False

    @staticmethod
    def get_spans_by_trace_id(trace_id: str) -> list[dict]:
        try:
            logger.info(f"Buscando spans da requisição {trace_id}")

            docs = list(
                TracesRepository.traces_collection.find(
                    {"trace_id": trace_id}
                ).sort("started_at", ASCENDING)
            )

            logger.info(f"Requisição {trace_id} tem {len(docs)} spans")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar spans da requisição {trace_id}")
            return []
