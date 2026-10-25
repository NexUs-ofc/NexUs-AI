from datetime import UTC, datetime

from bson import ObjectId


class Recipe:
    def __init__(self, title: str, serving_size: int, ingredients: list[dict],
                 instructions: str, account_id: int | None, created_by: str = "ai",
                 _id: ObjectId | None = None, preparation_time_minutes: int | None = None,
                 difficulty: str | None = None, created_at: datetime | None = None):
        self.id = _id
        self.title = title
        self.serving_size = serving_size
        self.ingredients = ingredients
        self.instructions = instructions
        self.account_id = account_id
        self.created_by = created_by
        self.preparation_time_minutes = preparation_time_minutes
        self.difficulty = difficulty
        self.created_at = created_at

    def to_dict(self) -> dict:
        doc = {
            "title": self.title, "serving_size": self.serving_size,
            "ingredients": self.ingredients, "instructions": self.instructions,
            "account_id": self.account_id, "created_by": self.created_by,
            "preparation_time_minutes": self.preparation_time_minutes,
            "difficulty": self.difficulty, "created_at": self.created_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"), title=data["title"], serving_size=data["serving_size"],
            ingredients=data["ingredients"], instructions=data["instructions"],
            account_id=data.get("account_id"), created_by=data.get("created_by", "ai"),
            preparation_time_minutes=data.get("preparation_time_minutes"),
            difficulty=data.get("difficulty"), created_at=data.get("created_at"),
        )

    def mark_created(self):
        self.created_at = self.created_at or datetime.now(UTC)

    def __repr__(self):
        return f"Recipe(id={self.id}, title={self.title!r}, account_id={self.account_id})"
