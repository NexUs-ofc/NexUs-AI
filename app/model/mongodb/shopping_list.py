import math
import re
from uuid import uuid4

from bson import ObjectId


def normalize_item(item: dict) -> dict:
    """Formato compartilhado com ShoppingListItem do Core, sem criar alimentos."""
    if not isinstance(item, dict):
        raise TypeError("Cada item deve informar nome, quantidade e unidade.")
    name = str(item.get("name") or item.get("nome") or item.get("ingredient") or item.get("ingrediente") or "").strip()
    if not name:
        raise ValueError("Informe o nome de todos os itens.")
    quantity = item.get("quantity", item.get("quantidade", item.get("quantidade_total")))
    unit = str(item.get("unitOfMeasure") or item.get("unit") or item.get("unidade") or "").strip()
    if isinstance(quantity, str):
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?)\s*(.*?)\s*", quantity)
        if not match:
            raise ValueError(f"Informe uma quantidade numérica para {name}.")
        number, suffix = match.groups()
        if "/" in number:
            numerator, denominator = number.split("/")
            quantity = float(numerator.replace(",", ".")) / float(denominator)
        else:
            quantity = float(number.replace(",", "."))
        unit = unit or suffix
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity <= 0:
        raise TypeError(f"A quantidade de {name} deve ser positiva.")
    if not unit:
        raise ValueError(f"Informe a unidade de {name}, como g, ml ou unidade.")
    checked = item.get("checked", item.get("purchased", item.get("comprado", False)))
    if not isinstance(checked, bool):
        raise TypeError("O estado comprado deve ser verdadeiro ou falso.")
    food_id = item.get("foodId", item.get("food_id"))
    if food_id is not None and (isinstance(food_id, bool) or not isinstance(food_id, int) or food_id <= 0):
        raise TypeError("Identificador de alimento inválido.")
    return {
        "id": str(item.get("id") or uuid4()),
        "foodId": food_id,
        "name": name,
        "quantity": quantity,
        "unitOfMeasure": unit,
        "checked": checked,
    }


class ShoppingList:
    def __init__(self, household_id: int, title: str, items: list[dict],
                 event_id: str | None = None, _id: ObjectId | None = None):
        self.id = _id
        self.household_id = household_id
        self.title = title.strip()
        if not self.title:
            raise ValueError("Informe o título da lista.")
        self.items = [normalize_item(item) for item in items]
        self.event_id = str(event_id) if event_id else None

    def to_dict(self) -> dict:
        doc = {
            "household_id": self.household_id,
            "title": self.title,
            "array_list": self.items,
            "event_id": self.event_id,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            _id=data.get("_id"), household_id=data["household_id"],
            title=data["title"], items=data.get("array_list", data.get("items", [])),
            event_id=data.get("event_id"),
        )

    def __repr__(self):
        return f"ShoppingList(id={self.id}, title={self.title!r}, items={len(self.items)})"
