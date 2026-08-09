from bson import ObjectId
from datetime import datetime


class Event:

    def __init__(
        self,
        title: str,
        description: str,
        date: datetime,
        duration: int,
        local: str,
        qtd_people: int,
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.title = title
        self.description = description
        self.date = date
        self.duration = duration
        self.local = local
        self.qtd_people = qtd_people

    def to_dict(self) -> dict:
        doc = {
            "title": self.title,
            "description": self.description,
            "date": self.date,
            "duration": self.duration,
            "local": self.local,
            "qtd_people": self.qtd_people,
        }

        if self.id is not None:
            doc["_id"] = self.id

        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"),
            title=data["title"],
            description=data["description"],
            date=data["date"],
            duration=data["duration"],
            local=data["local"],
            qtd_people=data["qtd_people"],
        )

    def __repr__(self):
        return (
            f"Event("
            f"id={self.id}, "
            f"title='{self.title}', "
            f"date={self.date}, "
            f"local='{self.local}'"
            f")"
        )