from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class ActivityRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")

    knowledge_collection = db.get_collection("knowledge")
    conversations_collection = db.get_collection("conversations")
    recipes_collection = db.get_collection("recipes")
    recipe_accounts_collection = db.get_collection("recipe_accounts")
    events_collection = db.get_collection("events")
    records_collection = db.get_collection("records")

    @staticmethod
    def get_knowledge(household_id: int, limite: int = 10) -> list[dict]:
        """
        Fatos já registrados sobre o usuário na collection knowledge.
        """

        try:
            docs = list(
                ActivityRepository.knowledge_collection.find(
                    {"household_id": household_id},
                    {"_id": 0, "fact": 1, "knowledge_type": 1, "ai_guideline": 1},
                ).limit(limite)
            )

            logger.info(f"Household {household_id} tem {len(docs)} fatos em knowledge")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar knowledge do household {household_id}")
            return []

    @staticmethod
    def get_conversas_recentes(account_id: int, limite: int = 5) -> list[list[dict]]:
        """
        Históricos das conversas mais recentes da conta.
        """

        try:
            docs = list(
                ActivityRepository.conversations_collection.find(
                    {
                        "account_id": account_id,
                        "historico.0": {"$exists": True},
                    },
                    {"_id": 0, "historico": 1},
                )
                .sort("created_at", -1)
                .limit(limite)
            )

            historicos = [d.get("historico", []) for d in docs if d.get("historico")]

            logger.info(f"Conta {account_id} tem {len(historicos)} conversas recentes")

            return historicos

        except PyMongoError:
            logger.exception(f"Erro ao buscar conversas da conta {account_id}")
            return []

    @staticmethod
    def get_receitas_recentes(account_id: int, limite: int = 5) -> list[dict]:
        """
        Receitas vinculadas à conta, das mais recentes para as mais antigas.
        """

        try:
            vinculos = list(
                ActivityRepository.recipe_accounts_collection.find(
                    {"id_account": account_id},
                    {"_id": 0, "id_recipe": 1},
                )
                .sort("created_at", -1)
                .limit(limite)
            )

            ids = [v["id_recipe"] for v in vinculos if v.get("id_recipe")]

            if not ids:
                return []

            docs = list(
                ActivityRepository.recipes_collection.find(
                    {"_id": {"$in": ids}},
                    {"_id": 0, "title": 1, "is_liked": 1, "serving_size": 1},
                )
            )

            logger.info(f"Conta {account_id} tem {len(docs)} receitas recentes")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar receitas da conta {account_id}")
            return []

    @staticmethod
    def get_eventos_recentes(household_id: int, limite: int = 5) -> list[dict]:
        """
        Eventos mais recentes do household.
        """

        try:
            docs = list(
                ActivityRepository.events_collection.find(
                    {"household_id": household_id},
                    {"_id": 0, "title": 1, "description": 1, "qtd_people": 1},
                )
                .sort("date", -1)
                .limit(limite)
            )

            logger.info(f"Household {household_id} tem {len(docs)} eventos recentes")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar eventos do household {household_id}")
            return []

    @staticmethod
    def get_registros_recentes(account_id: int, limite: int = 10) -> list[dict]:
        """
        Registros de comportamento (consumo, descarte, favoritos) mais recentes.
        """

        try:
            docs = list(
                ActivityRepository.records_collection.find(
                    {"account_id": account_id},
                    {"_id": 0, "event_type": 1, "details": 1},
                )
                .sort("date", -1)
                .limit(limite)
            )

            logger.info(f"Conta {account_id} tem {len(docs)} registros recentes")

            return docs

        except PyMongoError:
            logger.exception(f"Erro ao buscar registros da conta {account_id}")
            return []
