
from bson import ObjectId


class Recipe:

    def __init__(
        self,
        title: str,
        serving_size: int,
        ingredients: list[dict],
        instructions: str,
        is_liked: bool = False,
        created_by: str = "ai",
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.title = title
        self.serving_size = serving_size
        self.ingredients = ingredients
        self.instructions = instructions
        self.is_liked = is_liked
        self.created_by = created_by

    def to_dict(self) -> dict:
        doc = {
            "title": self.title,
            "serving_size": self.serving_size,
            "ingredients": self.ingredients,
            "instructions": self.instructions,
            "is_liked": self.is_liked,
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
            is_liked=data.get("is_liked", False),
            created_by=data.get("created_by", "ai"),
        )

    def __repr__(self):
        return (
            f"Recipe("
            f"id={self.id}, "
            f"title='{self.title}', "
            f"serving_size={self.serving_size}, "
            f"is_liked={self.is_liked}"
            f")"
        )