import unicodedata

DEFAULT_CATEGORIES = [
    "Hortifruti",
    "Carnes e Peixes",
    "Frios e Laticínios",
    "Padaria",
    "Congelados",
    "Mercearia",
    "Bebidas",
    "Doces e Snacks",
    "Higiene",
    "Limpeza",
    "Pet",
    "Outros",
]

SHELF_LIFE_DAYS = {
    "hortifruti": 7,
    "carnes e peixes": 3,
    "frios e laticinios": 10,
    "padaria": 5,
    "congelados": 90,
    "mercearia": 180,
    "bebidas": 180,
    "doces e snacks": 180,
    "higiene": 730,
    "limpeza": 730,
    "pet": 365,
    "outros": 30,
}

FALLBACK_DAYS = 30

NON_FOOD_CATEGORIES = {
    "higiene",
    "limpeza",
    "pet",
    "bazar",
    "utilidades",
    "vestuario",
    "farmacia",
}


def _key(category: str) -> str:
    s = unicodedata.normalize("NFKD", category).encode("ascii", "ignore").decode()
    return s.strip().lower()


def shelf_life_days(category: str | None, llm_guess: int | None = None) -> int:
    if category and _key(category) in SHELF_LIFE_DAYS:
        return SHELF_LIFE_DAYS[_key(category)]
    if llm_guess:
        return max(1, min(int(llm_guess), 1095))
    return FALLBACK_DAYS


def is_storable_food(category: str | None) -> bool:
    if not category:
        return True
    return _key(category) not in NON_FOOD_CATEGORIES
