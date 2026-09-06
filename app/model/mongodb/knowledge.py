from bson import ObjectId


class Knowledge:

    def __init__(
        self,
        account_id: int,
        identity: dict,
        preferences: dict,
        household_id: int | None = None,
        _id: ObjectId | None = None
    ):
        self.id = _id
        self.account_id = account_id
        self.household_id = household_id
        self.identity = identity
        self.preferences = preferences

    def to_dict(self) -> dict:
        doc = {
            "account_id": self.account_id,
            "household_id": self.household_id,
            "identity": self.identity,
            "preferences": self.preferences,
        }

        if self.id is not None:
            doc["_id"] = self.id

        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"),
            account_id=data.get("account_id"),
            household_id=data.get("household_id"),
            identity=data.get("identity", {}),
            preferences=data.get("preferences", {}),
        )

    def __repr__(self):
        return (
            f"Knowledge("
            f"id={self.id}, "
            f"account_id={self.account_id}, "
            f"household_id={self.household_id}"
            f")"
        )