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
            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id)}
            )

            if doc is None:
                return []

            return doc.get("historico", [])

        except PyMongoError:
            logger.exception("Erro ao buscar histórico")
            return []

    @staticmethod
    def append_messages(session_id: str, user_msg: str, assistant_msg: str):
        try:
            ConversationsRepository.conversations_collection.update_one(
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

        except PyMongoError:
            logger.exception("Erro ao salvar mensagens")