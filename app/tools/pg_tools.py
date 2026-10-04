import json
from datetime import date, datetime

from langchain.tools import tool

from ..model.pgsql.food import Food
from ..model.pgsql.pantry_item import Pantry_Item
from ..repository.pgsql.config import SessionLocal
from ..repository.pgsql.food import FoodRepository
from ..repository.pgsql.stock import StockRepository

# O schema gerado a partir de `date` exige AAAA-MM-DD, e o modelo repete o
# formato que o usuario escreveu — em portugues, 20/10/2026. O Groq recusa a
# chamada antes de chegar aqui, entao a data entra como texto.
_FORMATOS_DATA = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
)


def _para_data(valor: str | None) -> date | None:
    """Converte a validade recebida do modelo. None quando nao vem nada."""

    if valor is None or isinstance(valor, date):
        return valor

    texto = str(valor).strip()

    if not texto:
        return None

    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()  # noqa: DTZ007
        except ValueError:
            continue

    raise ValueError(
        f"Data '{texto}' nao reconhecida. Use AAAA-MM-DD ou DD/MM/AAAA."
    )


def _food_lookup(session) -> dict[int, Food]:
    return {
        food.id: food
        for food in FoodRepository(session).get_foods()
    }


def _pantry_item_to_dict(item: Pantry_Item, foods: dict[int, Food]) -> dict:
    food = foods.get(item.food_id)

    return {
        "pantry_item_id": item.id,
        "food_id": item.food_id,
        "food_name": food.name if food else None,
        "quantity": item.quantity,
        "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
    }


def _to_json(data: list[dict], mensagem_vazio: str) -> str:
    if not data:
        return mensagem_vazio

    return json.dumps(data, ensure_ascii=False, default=str)


@tool("resolver_alimento")
def resolver_alimento(
    nome: str,
    categoria: str | None = None,
) -> str:
    """
    Resolve o nome de um alimento no food_id correspondente, cadastrando-o
    quando ainda não existir no catálogo.

    Use sempre que precisar de um food_id a partir do nome que o usuário falou,
    antes de add_product. Nunca peça o food_id ao usuário nem desista porque o
    alimento não estava cadastrado.

    Parâmetros:
        - nome: Nome do alimento como o usuário falou. Ex: "alface", "tomate".
        - categoria: Categoria do alimento, quando souber. Ex: "Hortifruti".
          Sem ela, o alimento entra em "Outros".

    Retorno:
        - Um alimento encontrado: {"food_id": X, "food_name": "...", "criado": false}
        - Vários encontrados: {"ambiguo": true, "opcoes": [...]} — pergunte ao
          usuário qual deles antes de seguir.
        - Nenhum encontrado: cadastra e devolve {"criado": true, ...}
    """

    with SessionLocal() as session:
        repository = FoodRepository(session)

        encontrados = repository.buscar_por_nome(nome)

        if len(encontrados) == 1:
            food = encontrados[0]

            return json.dumps(
                {"food_id": food.id, "food_name": food.name, "criado": False},
                ensure_ascii=False,
            )

        if len(encontrados) > 1:
            return json.dumps(
                {
                    "ambiguo": True,
                    "opcoes": [
                        {"food_id": f.id, "food_name": f.name, "marca": f.product_brand}
                        for f in encontrados[:10]
                    ],
                },
                ensure_ascii=False,
            )

        food = repository.criar(nome=nome, categoria=categoria)

        if food is None:
            return json.dumps(
                {"erro": f"Não foi possível cadastrar o alimento '{nome}'."},
                ensure_ascii=False,
            )

        return json.dumps(
            {"food_id": food.id, "food_name": food.name, "criado": True},
            ensure_ascii=False,
        )


@tool("add_product")
def add_product(
    profile_id: int,
    food_id: int,
    quantity: int,
    expiry_date: str,
) -> str:
    """
    Adiciona um produto ao estoque do usuário.

    Parâmetros:
        - profile_id: Id do perfil do usuário.
        - food_id: Id do alimento.
        - quantity: Quantidade disponível.
        - expiry_date: Data de vencimento, no formato "AAAA-MM-DD".

    Se o usuário já tiver esse mesmo alimento com essa mesma validade no
    estoque, a quantidade é somada à linha existente.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        validade = _para_data(expiry_date)

        # Mesmo alimento e mesma validade somam na linha que ja existe, em
        # vez de virar duplicata.
        existente = repository.find_equivalente(
            profile_id=profile_id,
            food_id=food_id,
            expiry_date=validade,
        )

        if existente is not None:
            existente.quantity += quantity
            pantry_item = existente
        else:
            pantry_item = Pantry_Item(
                profile_id=profile_id,
                food_id=food_id,
                quantity=quantity,
                expiry_date=validade,
            )

        salvo = repository.save(pantry_item)

        if salvo is None:
            return "Erro ao adicionar produto ao estoque."

        foods = _food_lookup(session)

        return _to_json(
            [_pantry_item_to_dict(salvo, foods)],
            "Erro ao adicionar produto ao estoque.",
        )


@tool("remove_product")
def remove_product(
    pantry_item_id: int,
) -> bool:
    """
    Remove um produto do estoque do usuário.

    Parâmetros:
        - pantry_item_id: Identificador do item no estoque.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        pantry_item = repository.find_by_id(pantry_item_id)

        if pantry_item is None:
            return False

        return repository.remove_product(pantry_item)


@tool("get_stock")
def get_stock(
    profile_id: int,
) -> str:
    """
    Lista todo o estoque do usuário.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        itens = repository.get_stock(profile_id)
        foods = _food_lookup(session)

        return _to_json(
            [_pantry_item_to_dict(item, foods) for item in itens],
            "O usuário não possui nenhum produto cadastrado no estoque.",
        )


@tool("get_expired_products")
def get_expired_products(
    profile_id: int,
) -> str:
    """
    Lista produtos vencidos ou próximos do vencimento.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        itens = repository.get_expired_products(profile_id)
        foods = _food_lookup(session)

        return _to_json(
            [_pantry_item_to_dict(item, foods) for item in itens],
            "Não há produtos vencidos ou próximos do vencimento.",
        )


@tool("get_missing_products")
def get_missing_products(
    profile_id: int,
) -> str:
    """
    Lista produtos cuja quantidade está abaixo do mínimo configurado.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        rows = repository.get_missing_products(profile_id)
        foods = _food_lookup(session)

        data = [
            {
                "food_id": row.food_id,
                "food_name": (
                    foods[row.food_id].name
                    if row.food_id in foods
                    else None
                ),
                "quantity": row.quantity,
                "minimum_quantity": row.minimum_quantity,
            }
            for row in rows
        ]

        return _to_json(
            data,
            "Não há produtos em falta no momento.",
        )


@tool("get_category_info")
def get_category_info(
    profile_id: int,
) -> str:
    """
    Retorna um relatório de produtos agrupados por categoria.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        rows = repository.get_category_info(profile_id)

        data = [
            {
                "categoria": row.category_name,
                "total_produtos": row.total_products,
            }
            for row in rows
        ]

        return _to_json(
            data,
            "Não há produtos suficientes no estoque para gerar um relatório por categoria.",
        )


@tool("get_brand_info")
def get_brand_info(
    profile_id: int,
) -> str:
    """
    Retorna um relatório de produtos agrupados por marca.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        rows = repository.get_brand_info(profile_id)

        data = [
            {
                "marca": row.product_brand,
                "total_produtos": row.total_products,
            }
            for row in rows
        ]

        return _to_json(
            data,
            "Não há produtos suficientes no estoque para gerar um relatório por marca.",
        )


@tool("get_foods")
def get_foods() -> str:
    """
    Lista todos os alimentos cadastrados.

    Utilize esta ferramenta antes de adicionar um produto ao estoque
    quando for necessário descobrir qual é o food_id correspondente.

    Parâmetros:
        Nenhum.
    """

    with SessionLocal() as session:
        repository = FoodRepository(session)

        foods = repository.get_foods()

        data = [
            {
                "food_id": food.id,
                "name": food.name,
                "category_id": food.category_id,
                "product_brand": food.product_brand,
                "package_quantity": float(food.package_quantity),
                "unit_of_measure": food.unit_of_measure,
            }
            for food in foods
        ]

        return _to_json(
            data,
            "Nenhum alimento cadastrado no sistema.",
        )