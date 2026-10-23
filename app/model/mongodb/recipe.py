
from bson import ObjectId


class Recipe:

    def __init__(
        self,
        title: str,
        serving_size: int,
        ingredients: list[dict],
        instructions: str,
        account_id: int | None,
        created_by: str = "ai",
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.title = title
        self.serving_size = serving_size
        self.ingredients = ingredients
        self.instructions = instructions
        self.account_id = account_id
        self.created_by = created_by

    def to_dict(self) -> dict:
        doc = {
            "title": self.title,
            "serving_size": self.serving_size,
            "ingredients": self.ingredients,
            "instructions": self.instructions,
            "account_id": self.account_id,
            "created_by": self.created_by,
        }

        if self.id is not None:
            doc["_id"] = self.id

        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"),
            title=data["title"],
            serving_size=data["serving_size"],
            ingredients=data["ingredients"],
            instructions=data["instructions"],
            # Receita antiga (do tempo do recipe_accounts) nao tem account_id.
            account_id=data.get("account_id"),
            created_by=data.get("created_by", "ai"),
        )

    def __repr__(self):
        return (
            f"Recipe("
            f"id={self.id}, "
            f"title='{self.title}', "
            f"serving_size={self.serving_size}, "
            f"account_id={self.account_id}"
            f")"
        )