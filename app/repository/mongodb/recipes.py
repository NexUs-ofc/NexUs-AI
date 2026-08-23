from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import datetime

from ...model.mongodb.recipe import Recipe
from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)


class RecipesRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    recipes_collection = db.get_collection("recipes")
    recipe_accounts_collection = db.get_collection("recipe_accounts")

    @staticmethod
    def create_recipe(recipe: Recipe, account_id: int) -> Recipe | None:
        try:
            logger.info("Inserindo receita no MongoDB")

            result = RecipesRepository.recipes_collection.insert_one(recipe.to_dict())
            recipe.id = result.inserted_id

            RecipesRepository.recipe_accounts_collection.insert_one({
                "id_recipe": recipe.id,
                "id_account": account_id,
                "created_at": datetime.now(),
            })

            logger.info("Receita inserida com sucesso")

            return recipe

        except PyMongoError:
            logger.exception("Erro ao inserir receita no MongoDB")
            return None

    @staticmethod
    def get_recipe_by_id(recipe_id: str | ObjectId) -> Recipe | None:
        try:
            logger.info(f"Buscando receita {recipe_id}")

            if isinstance(recipe_id, str):
                recipe_id = ObjectId(recipe_id)

            doc = RecipesRepository.recipes_collection.find_one({"_id": recipe_id})

            if doc is None:
                return None

            return Recipe.from_dict(doc)

        except PyMongoError:
            logger.exception(f"Erro ao buscar receita {recipe_id}")
            return None

    @staticmethod
    def get_user_recipes(account_id: int, limite: int = 5) -> list[Recipe]:
        try:
            logger.info("Buscando receitas do usuário")

            vinculos = RecipesRepository.recipe_accounts_collection.find(
                {"id_account": account_id}
            )
            recipe_ids = [v["id_recipe"] for v in vinculos]

            if not recipe_ids:
                return []

            docs = RecipesRepository.recipes_collection.find(
                {"_id": {"$in": recipe_ids}}
            ).limit(limite)

            logger.info("Receitas listadas com sucesso")

            return [Recipe.from_dict(doc) for doc in docs]

        except PyMongoError:
            logger.exception("Erro ao buscar receitas do usuário")
            return []