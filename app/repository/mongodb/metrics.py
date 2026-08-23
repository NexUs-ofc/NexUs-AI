from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class MetricsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    metrics_collection = db.get_collection("metrics")

    @staticmethod
    def save_request_metric(
        trace_id: str,
        route: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: float,
        tool_calls: int,
        error: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> bool:
        try:
            logger.info(f"Salvando métrica de requisição {trace_id}")

            MetricsRepository.metrics_collection.insert_one({
                "trace_id": trace_id,
                "route": route,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "tool_calls": tool_calls,
                "error": error,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            })

            logger.info(f"Métrica de requisição {trace_id} salva com sucesso")

            return True

        except PyMongoError:
            logger.exception(f"Erro ao salvar métrica de requisição {trace_id}")
            return False
