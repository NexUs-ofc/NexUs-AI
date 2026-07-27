from bson import ObjectId
from datetime import datetime


class Recipe:

    def __init__(
        self,
        title: str,
        array_ingredients: str,
        instructions: str,
        is_liked: bool = False,
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.title = title
        self.array_ingredients = array_ingredients
        self.instructions = instructions
        self.is_liked = is_liked

    def to_dict(self) -> dict:
        doc = {
            "title": self.title,
            "array_ingredients": self.array_ingredients,
            "instructions": self.instructions,
            "is_liked": self.is_liked,
        }

        if self.id is not None:
            doc["_id"] = self.id

        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"),
            title=data["title"],
            array_ingredients=data["array_ingredients"],
            instructions=data["instructions"],
            is_liked=data.get("is_liked", False),
        )

    def __repr__(self):
        return (
            f"Recipe("
            f"id={self.id}, "
            f"title='{self.title}', "
            f"is_liked={self.is_liked}"
            f")"
        )
