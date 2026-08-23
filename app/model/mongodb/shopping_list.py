from bson import ObjectId


class ShoppingList:

    def __init__(
        self,
        household_id: int,
        title: str,
        items: list[dict],
        event_id: ObjectId | None = None,
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.household_id = household_id
        self.title = title
        self.items = items
        self.event_id = event_id

    def to_dict(self) -> dict:
        doc = {
            "household_id": self.household_id,
            "title": self.title,
            "items": self.items,
            "event_id": self.event_id,
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
            items=data["items"],
            event_id=data.get("event_id"),
        )

    def __repr__(self):
        return (
            f"ShoppingList("
            f"id={self.id}, "
            f"household_id={self.household_id}, "
            f"title='{self.title}', "
            f"items={len(self.items)}"
            f")"
        )