from datetime import datetime

from bson import ObjectId


class Event:

    def __init__(
        self,
        household_id: int,
        title: str,
        description: str,
        date: datetime,
        duration: int,
        local: str,
        qtd_people: int,
        recipes: list[dict] | None = None,
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.household_id = household_id
        self.title = title
        self.description = description
        self.date = date
        self.duration = duration
        self.local = local
        self.qtd_people = qtd_people
        self.recipes = recipes if recipes is not None else []

    def to_dict(self) -> dict:
        doc = {
            "household_id": self.household_id,
            "title": self.title,
            "description": self.description,
            "date": self.date,
            "duration": self.duration,
            "local": self.local,
            "qtd_people": self.qtd_people,
            "recipes": self.recipes,
        }

        if self.id is not None:
            doc["_id"] = self.id

        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"),
            household_id=data["household_id"],
            title=data["title"],
            description=data["description"],
            date=data["date"],
            duration=data["duration"],
            local=data["local"],
            qtd_people=data["qtd_people"],
            recipes=data.get("recipes", []),
        )

    def __repr__(self):
        return (
            f"Event("
            f"id={self.id}, "
            f"household_id={self.household_id}, "
            f"title='{self.title}', "
            f"date={self.date}, "
            f"local='{self.local}'"
            f")"
        )