from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...model.mongodb.knowledge import Knowledge
from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class KnowledgeRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    knowledge_collection = db.get_collection("knowledge")

    @staticmethod
    def get_knowledge(account_id: int, household_id: int | None = None) -> Knowledge | None:
        try:
            logger.info(f"Buscando conhecimento do usuário {account_id}")

            query = {"$or": [{"account_id": account_id}]}

            if household_id is not None:
                query["$or"].append({"household_id": household_id})

            doc = KnowledgeRepository.knowledge_collection.find_one(query)

            if doc is None:
                logger.info(f"Conhecimento do usuário {account_id} não encontrado")
                return None

            logger.info(f"Conhecimento do usuário {account_id} encontrado com sucesso")

            return Knowledge.from_dict(doc)

        except PyMongoError:
            logger.exception(f"Erro ao buscar conhecimento do usuário {account_id}")
            return None