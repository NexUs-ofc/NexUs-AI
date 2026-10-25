"""Cálculo de compras a partir de uma receita, sem estimativas do modelo."""

import json
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from langchain.tools import tool

from ..model.mongodb.shopping_list import normalize_item
from .pg_tools import get_stock

UNITS = {
    "g": ("mass", Decimal(1)), "grama": ("mass", Decimal(1)), "gramas": ("mass", Decimal(1)),
    "kg": ("mass", Decimal(1000)), "quilo": ("mass", Decimal(1000)),
    "ml": ("volume", Decimal(1)), "l": ("volume", Decimal(1000)),
    "litro": ("volume", Decimal(1000)), "litros": ("volume", Decimal(1000)),
    "un": ("unit", Decimal(1)), "unit": ("unit", Decimal(1)),
    "unidade": ("unit", Decimal(1)), "unidades": ("unit", Decimal(1)),
    "pacote": ("package", Decimal(1)), "pacotes": ("package", Decimal(1)),
}


def _name(value: str) -> str:
    return " ".join(
        "".join(c for c in unicodedata.normalize("NFKD", value.lower())
                if not unicodedata.combining(c)).split()
    )


def calculate_missing(ingredients: list[dict], stock: list[dict], today: date) -> dict:
    """Soma lotes válidos e compara apenas unidades que podem ser convertidas."""
    normalized = [normalize_item(item) for item in ingredients]
    # Necessidades repetidas da mesma receita devem ser somadas antes do desconto.
    grouped = {}
    for item in normalized:
        unit = UNITS.get(_name(item["unitOfMeasure"]))
        key = (_name(item["name"]), unit[0] if unit else _name(item["unitOfMeasure"]))
        if key in grouped:
            first = UNITS.get(_name(grouped[key]["unitOfMeasure"]))
            ratio = unit[1] / first[1] if unit and first else Decimal(1)
            grouped[key]["quantity"] += float(Decimal(str(item["quantity"])) * ratio)
        else:
            grouped[key] = item.copy()

    checks, missing = [], []
    for item in grouped.values():
        if _name(item["name"]) in {"agua", "agua filtrada", "agua potavel"}:
            checks.append({"nome": item["name"], "quantidade_necessaria": item["quantity"],
                           "unidade": item["unitOfMeasure"], "quantidade_disponivel": None,
                           "tem_suficiente": False, "comparacao_confirmada": False,
                           "dispensa_compra": True})
            continue
        matches = [s for s in stock if _name(str(s.get("food_name") or "")) == _name(item["name"])]
        need_unit = UNITS.get(_name(item["unitOfMeasure"]))
        available = Decimal(0)
        comparable = bool(matches and need_unit)
        for record in matches:
            expiry = record.get("expiry_date")
            if not expiry:
                continue
            try:
                if date.fromisoformat(str(expiry)[:10]) < today:
                    continue
            except ValueError:
                comparable = False
                continue
            packages = Decimal(str(record.get("quantity") or 0))
            if need_unit and need_unit[0] == "package":
                available += packages
                continue
            have_unit = UNITS.get(_name(str(record.get("unit_of_measure") or "")))
            size = record.get("package_quantity")
            if not need_unit or not have_unit or need_unit[0] != have_unit[0] or size is None:
                comparable = False
                continue
            available += packages * Decimal(str(size)) * have_unit[1] / need_unit[1]
        need = Decimal(str(item["quantity"]))
        amount = max(Decimal(0), need - available) if comparable else need
        checks.append({
            "nome": item["name"], "quantidade_necessaria": float(need),
            "unidade": item["unitOfMeasure"],
            "quantidade_disponivel": float(available) if comparable else None,
            "tem_suficiente": comparable and available >= need,
            "comparacao_confirmada": comparable,
        })
        if amount > 0:
            missing.append({
                "name": item["name"], "quantity": float(amount),
                "unitOfMeasure": item["unitOfMeasure"], "checked": False,
            })
    return {"itens_para_comprar": missing, "conferencia": checks}


@tool("ingredientes_para_comprar")
def ingredientes_para_comprar(ingredientes: list[dict]) -> str:
    """Calcula o que falta para uma receita usando o estoque autenticado.
    ingredientes: todos os ingredientes e quantidades da receita, no formato
      [{"name": "Arroz", "quantity": 500, "unitOfMeasure": "g"}].
      Também aceita {"ingredient": "Arroz", "quantity": "500 g"}.
    Não invente quantidades ou converta medidas de cozinha em gramas.
    O retorno traz itens_para_comprar, conferência e se a comparação foi possível.
    Sem comparação confirmada, a quantidade toda vai para conferência de compra:
    avise a pessoa; não afirme que tem ou não tem quantidade suficiente.
    Nunca grava dados.
    """
    if not ingredientes:
        return "FALHA: informe os ingredientes da receita."
    response = get_stock.invoke({})
    if response.startswith("FALHA"):
        return response
    try:
        stock = json.loads(response) if response.startswith("[") else []
        result = calculate_missing(ingredientes, stock, date.today())
    except (ValueError, TypeError, ZeroDivisionError, InvalidOperation):
        return "FALHA: informe nome, quantidade numérica e unidade de cada ingrediente."
    return json.dumps(result, ensure_ascii=False)
