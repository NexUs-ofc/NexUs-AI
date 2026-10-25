import re

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, PyMongoError, WTimeoutError

from ...config import MONGODB_URI
from ...controller.config import logging
from ...model.mongodb.shopping_list import ShoppingList

logger = logging.getLogger(__name__)


class ShoppingListUnavailable(RuntimeError):
    """Falha de consulta não significa lista inexistente."""


class ShoppingListsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    shopping_lists_collection = db.get_collection("shopping_list")

    @staticmethod
    def create_list(shopping_list: ShoppingList) -> ShoppingList | None:
        try:
            result = ShoppingListsRepository.shopping_lists_collection.insert_one(shopping_list.to_dict())
            shopping_list.id = result.inserted_id
            return shopping_list
        except (AutoReconnect, WTimeoutError):
            raise
        except PyMongoError:
            logger.exception("Erro ao criar lista de compras")
            return None

    @staticmethod
    def get_list(list_id: str | ObjectId, household_id: int) -> ShoppingList | None:
        if not ObjectId.is_valid(list_id):
            return None
        try:
            doc = ShoppingListsRepository.shopping_lists_collection.find_one(
                {"_id": ObjectId(list_id), "household_id": household_id}
            )
            return ShoppingList.from_dict(doc) if doc else None
        except (PyMongoError, ValueError, TypeError, KeyError) as error:
            logger.exception("Erro ao consultar lista de compras")
            raise ShoppingListUnavailable("Não foi possível consultar a lista.") from error

    @staticmethod
    def get_lists(household_id: int, title: str = "", limit: int = 20) -> list[ShoppingList]:
        query = {"household_id": household_id}
        if title.strip():
            query["title"] = {"$regex": re.escape(title.strip()), "$options": "i"}
        try:
            docs = ShoppingListsRepository.shopping_lists_collection.find(query).sort("_id", -1).limit(limit)
            return [ShoppingList.from_dict(doc) for doc in docs]
        except (PyMongoError, ValueError, TypeError, KeyError) as error:
            logger.exception("Erro ao buscar listas de compras")
            raise ShoppingListUnavailable("Não foi possível buscar as listas.") from error

    @staticmethod
    def update_list(list_id: str, household_id: int, items: list[dict],
                    title: str | None = None) -> ShoppingList | None:
        if not ObjectId.is_valid(list_id):
            return None
        changes = {"array_list": items}
        if title is not None:
            changes["title"] = title
        try:
            result = ShoppingListsRepository.shopping_lists_collection.update_one(
                {"_id": ObjectId(list_id), "household_id": household_id}, {"$set": changes},
            )
            if not result.matched_count:
                return None
            return ShoppingListsRepository.get_list(list_id, household_id)
        except (AutoReconnect, WTimeoutError):
            raise
        except (PyMongoError, ValueError, TypeError, KeyError) as error:
            logger.exception("Erro ao atualizar lista de compras")
            raise ShoppingListUnavailable("Não foi possível atualizar a lista.") from error
