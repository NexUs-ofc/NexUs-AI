from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class HallucinationReplaysRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    replays_collection = db.get_collection("hallucination_replays")

    @staticmethod
    def save_replay(
        trace_id: str,
        pergunta: str,
        resposta_original: str,
        veredito: str,
        evidencias: list[str],
        resposta_final: str,
        replay_executado: bool,
    ) -> bool:
        try:
            logger.info(f"Salvando replay de investigação de alucinação ({trace_id})")

            HallucinationReplaysRepository.replays_collection.insert_one({
                "trace_id": trace_id,
                "pergunta": pergunta,
                "resposta_original": resposta_original,
                "veredito": veredito,
                "evidencias": evidencias,
                "resposta_final": resposta_final,
                "replay_executado": replay_executado,
                "created_at": datetime.now(),
            })

            logger.info(f"Replay de investigação ({trace_id}) salvo com sucesso")

            return True

        except PyMongoError:
            logger.exception(f"Erro ao salvar replay de investigação ({trace_id})")
            return False

    @staticmethod
    def get_replays_by_trace_id(trace_id: str) -> list[dict]:
        try:
            logger.info(f"Buscando replays de investigação da requisição {trace_id}")

            docs = list(
                HallucinationReplaysRepository.replays_collection.find(
                    {"trace_id": trace_id}
                )
            )

            logger.info(f"Requisição {trace_id} tem {len(docs)} replays de investigação")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar replays de investigação da requisição {trace_id}")
            return []