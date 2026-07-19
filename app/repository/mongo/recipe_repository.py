import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.getenv("MONGO_URL"))
db = client[os.getenv("MONGO_DB", "ceris")]


class RecipeRepository:
    def __init__(self):
        self.recipes = db["MONGO_recipe"]
        self.recipe_accounts = db["MONGO_Recipe_account"]

    def buscar_receitas_usuario(self, account_id: int, limite: int = 5) -> list[dict]:
        vinculos = self.recipe_accounts.find({"id_account": account_id})
        ids = [v["id_repice"] for v in vinculos]

        if not ids:
            return []

        return list(self.recipes.find({"id": {"$in": ids}}).limit(limite))

    def salvar_receita(self, titulo: str, ingredientes: str, instrucoes: str, account_id: int) -> dict:
        ultimo = self.recipes.find_one(sort=[("id", -1)])
        recipe_id = (ultimo["id"] + 1) if ultimo else 1

        receita = {
            "id": recipe_id,
            "title": titulo,
            "array_ingredients": ingredientes,
            "instructions": instrucoes,
            "is_liked": False,
        }
        self.recipes.insert_one(receita)

        ultimo_v = self.recipe_accounts.find_one(sort=[("id", -1)])
        self.recipe_accounts.insert_one({
            "id": (ultimo_v["id"] + 1) if ultimo_v else 1,
            "id_repice": recipe_id,
            "id_account": account_id,
            "create_at": None,
        })

        return receita
