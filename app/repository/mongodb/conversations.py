from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

class ConversationRepository:
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client.get_database("db_ceris")
    collection = db.get_collection("")

    @staticmethod
    def get_history(account_id: int, limite: int = 20) -> list[dict]:
        doc = ConversationRepository.collection.find_one(
            {"account_id": account_id}
        )
        if not doc:
            return []
        return doc.get("messages", [])[-limite:]



    @staticmethod
    def append_messages(account_id: int, messages: list[dict]):
        ConversationRepository.collection.update_one(
            {"account_id": account_id},
            {"$push": {"messages": {"$each": messages}}},
            upsert=True,  # se não existir, cria
        )