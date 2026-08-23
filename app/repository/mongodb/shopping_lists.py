from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...model.mongodb.shopping_list import ShoppingList
from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class ShoppingListsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    shopping_lists_collection = db.get_collection("shopping_lists")

    @staticmethod
    def create_list(shopping_list: ShoppingList) -> ShoppingList | None:
        try:
            logger.info("Inserindo lista de compras no MongoDB")

            result = ShoppingListsRepository.shopping_lists_collection.insert_one(
                shopping_list.to_dict()
            )

            shopping_list.id = result.inserted_id

            logger.info("Lista de compras inserida com sucesso")

            return shopping_list

        except PyMongoError:
            logger.exception("Erro ao inserir lista de compras no MongoDB")
            return None

    @staticmethod
    def get_list(list_id: str | ObjectId) -> ShoppingList | None:
        try:
            logger.info(f"Buscando lista de compras {list_id}")

            if isinstance(list_id, str):
                list_id = ObjectId(list_id)

            doc = ShoppingListsRepository.shopping_lists_collection.find_one(
                {"_id": list_id}
            )

            if doc is None:
                return None

            return ShoppingList.from_dict(doc)

        except PyMongoError:
            logger.exception(f"Erro ao buscar lista de compras {list_id}")
            return None

    @staticmethod
    def update_list(list_id: str | ObjectId, items: list[dict]) -> ShoppingList | None:
        try:
            logger.info(f"Atualizando lista de compras {list_id}")

            if isinstance(list_id, str):
                list_id = ObjectId(list_id)

            result = ShoppingListsRepository.shopping_lists_collection.update_one(
                {"_id": list_id},
                {"$set": {"items": items}}
            )

            if result.matched_count == 0:
                logger.warning(f"Lista de compras {list_id} não encontrada")
                return None

            logger.info("Lista de compras atualizada com sucesso")

            return ShoppingListsRepository.get_list(list_id)

        except PyMongoError:
            logger.exception(f"Erro ao atualizar lista de compras {list_id}")
            return None