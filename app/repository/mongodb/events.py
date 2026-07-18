from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

from datetime import datetime
import os

from ..entities.mongodb.event import Event
from ...controller.config import logging

load_dotenv()

logger = logging.getLogger(__name__)

uri = os.getenv("MONGODB_URI")

client = MongoClient(uri)
db = client.get_database("db_ceris")
events_collection = db.get_collection("events")


def create_event(event: Event) -> Event | None:
    try:
        logger.info("Inserindo evento no MongoDB")

        result = events_collection.insert_one(event.to_dict())

        event.id = result.inserted_id

        logger.info("Evento inserido com sucesso no MongoDB")

        return event

    except PyMongoError:
        logger.exception("Erro ao inserir evento no MongoDB")
        return None


def get_events(
    start: datetime = None,
    end: datetime = None,
    type: str = None,
    qtd_min: int = None,
    recipes_titles: list[str] = None,
) -> list[Event]:

    query = {}

    if start or end:
        query["date"] = {}

        if start:
            query["date"]["$gte"] = start

        if end:
            query["date"]["$lte"] = end

    if type:
        query["description"] = {
            "$regex": type,
            "$options": "i"
        }

    if qtd_min is not None:
        query["qtd_people"] = {
            "$gte": qtd_min
        }

    if recipes_titles:
        query["recipes.title"] = {
            "$in": recipes_titles
        }

    try:
        logger.info("Listando eventos do MongoDB")

        docs = events_collection.find(query)

        logger.info("Eventos listados com sucesso")

        return [Event.from_dict(doc) for doc in docs]

    except PyMongoError:
        logger.exception("Erro ao listar eventos do MongoDB")
        return []


def update_event(event: Event) -> Event | None:
    try:
        logger.info(f"Atualizando evento {event.id}")

        result = events_collection.update_one(
            {"_id": event.id},
            {
                "$set": {
                    "description": event.description,
                    "date": event.date
                }
            }
        )

        if result.matched_count == 0:
            logger.warning(f"Evento {event.id} não encontrado")
            return None

        logger.info("Evento atualizado com sucesso")

        return event

    except PyMongoError:
        logger.exception(f"Erro ao atualizar evento {event.id}")
        return None


def delete_event(event_id: str | ObjectId) -> bool:
    try:
        logger.info(f"Removendo evento {event_id}")

        if isinstance(event_id, str):
            event_id = ObjectId(event_id)

        result = events_collection.delete_one(
            {"_id": event_id}
        )

        if result.deleted_count == 0:
            logger.warning(f"Evento {event_id} não encontrado")
            return False

        logger.info("Evento removido com sucesso")

        return True

    except PyMongoError:
        logger.exception(f"Erro ao remover evento {event_id}")
        return False