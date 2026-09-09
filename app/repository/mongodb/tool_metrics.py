from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class ToolMetricsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    tool_metrics_collection = db.get_collection("tool_metrics")

    @staticmethod
    def save_tool_call(
        trace_id: str,
        tool_name: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: float,
        success: bool,
    ) -> bool:
        try:
            logger.info(f"Salvando métrica de tool {tool_name} ({trace_id})")

            ToolMetricsRepository.tool_metrics_collection.insert_one({
                "trace_id": trace_id,
                "tool_name": tool_name,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "success": success,
            })

            logger.info(f"Métrica de tool {tool_name} ({trace_id}) salva com sucesso")

            return True

        except PyMongoError:
            logger.exception(f"Erro ao salvar métrica de tool {tool_name} ({trace_id})")
            return False

    @staticmethod
    def count_by_trace_id(trace_id: str) -> int:
        try:
            logger.info(f"Contando chamadas de tool da requisição {trace_id}")

            count = ToolMetricsRepository.tool_metrics_collection.count_documents(
                {"trace_id": trace_id}
            )

            logger.info(f"Requisição {trace_id} teve {count} chamadas de tool")

            return count

        except PyMongoError:
            logger.exception(f"Erro ao contar chamadas de tool da requisição {trace_id}")
            return 0
