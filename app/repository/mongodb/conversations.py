from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import datetime

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)

class ConversationsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    conversations_collection = db.get_collection("conversations")

    @staticmethod
    def create_session(account_id: int) -> str:
        try:
            result = ConversationsRepository.conversations_collection.insert_one({
                "account_id": account_id,
                "historico": [],
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            })

            logger.info(f"Sessão criada: {result.inserted_id}")

            return str(result.inserted_id)

        except PyMongoError:
            logger.exception("Erro ao criar sessão")
            return None

    @staticmethod
    def get_historico(session_id: str) -> list[dict]:
        try:
            logger.info(f"Buscando histórico da sessão {session_id}")

            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id)}
            )

            if doc is None:
                logger.info(f"Sessão {session_id} não encontrada")
                return []

            historico = doc.get("historico", [])

            logger.info(f"Histórico da sessão {session_id} carregado, {len(historico)} mensagens")

            return historico

        except PyMongoError:
            logger.exception("Erro ao buscar histórico")
            return []

    @staticmethod
    def sessao_ativa(session_id: str) -> bool:
        try:
            logger.info(f"Verificando se a sessão {session_id} está ativa")

            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id)}
            )

            ativa = doc is not None and doc.get("ended_at") is None

            logger.info(f"Sessão {session_id} ativa={ativa}")

            return ativa

        except PyMongoError:
            logger.exception(f"Erro ao verificar sessão {session_id}")
            return False

    @staticmethod
    def end_session(session_id: str) -> bool:
        try:
            logger.info(f"Finalizando sessão {session_id}")

            result = ConversationsRepository.conversations_collection.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": {
                        "ended_at": datetime.now(),
                        "status": "closed",
                    }
                }
            )

            logger.info(f"Sessão {session_id} finalizada, matched_count={result.matched_count}")

            return result.matched_count > 0

        except PyMongoError:
            logger.exception(f"Erro ao finalizar sessão {session_id}")
            return False

    @staticmethod
    def append_messages(session_id: str, user_msg: str, assistant_msg: str):
        try:
            logger.info(f"Salvando mensagens da sessão {session_id}")

            result = ConversationsRepository.conversations_collection.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$push": {
                        "historico": {
                            "$each": [
                                {"role": "user", "content": user_msg},
                                {"role": "assistant", "content": assistant_msg},
                            ]
                        }
                    },
                    "$set": {"updated_at": datetime.now()}
                }
            )

            logger.info(f"Mensagens da sessão {session_id} salvas, matched_count={result.matched_count}")

        except PyMongoError:
            logger.exception("Erro ao salvar mensagens")