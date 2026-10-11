from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, MongoClient
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

    @staticmethod
    def latencia_por_no(horas: int = 24) -> list[dict]:
        """
        p50 e p95 de cada nó do grafo na janela.

        É a pergunta "onde o tempo foi" respondida sem ler log: ordenado pelo
        p95, o primeiro da lista é onde mexer. Gravávamos cada span desde
        sempre e ninguém somava.
        """

        desde = datetime.now(UTC) - timedelta(hours=horas)

        try:
            logger.info(f"Agregando latência por nó das últimas {horas}h")

            etapas = [
                {"$match": {"started_at": {"$gte": desde}}},
                {"$group": {
                    "_id": "$span_name",
                    "execucoes": {"$sum": 1},
                    "duracoes": {"$push": "$duration_ms"},
                }},
            ]

            linhas = []

            for doc in TracesRepository.traces_collection.aggregate(etapas):
                duracoes = sorted(doc.get("duracoes") or [])

                if not duracoes:
                    continue

                def indice(posicao: int, total: int = len(duracoes)) -> int:
                    return min(total - 1, round((posicao / 100) * (total - 1)))

                linhas.append({
                    "no": doc["_id"] or "desconhecido",
                    "execucoes": doc["execucoes"],
                    "p50_ms": round(duracoes[indice(50)], 1),
                    "p95_ms": round(duracoes[indice(95)], 1),
                    "total_s": round(sum(duracoes) / 1000, 1),
                })

            return sorted(linhas, key=lambda linha: linha["p95_ms"], reverse=True)

        except PyMongoError:
            logger.exception("Erro ao agregar latência por nó")

            return []
