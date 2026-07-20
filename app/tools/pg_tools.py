from datetime import datetime
from decimal import Decimal

from langchain.tools import tool

from ..repository.pgsql.config import SessionLocal
from ..repository.entities.pgsql.pantry_item import Pantry_Item
from ..repository.entities.pgsql.food import Food
from ..repository.pgsql.stock import StockRepository
from ..repository.pgsql.food import FoodRepository


@tool("add_product")
def add_product(
    household_account_id: int,
    food_id: int,
    quantity: Decimal,
    expiry_date: datetime,
    minimum_quantity: Decimal,
    is_expired: bool = False
) -> Pantry_Item | None:
    """
    Adiciona um produto ao estoque do usuário.

    Parâmetros:
        - household_account_id: Id do usuário;
        - food_id: Id do alimento a ser adicionado;
        - quantity: Quantidade em decimal;
        - expiry_date: data de expiração em datetime;
        - minimum_quantity: Quantidade mínima em estoque antes de apitar falta do produto;
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        pantry_item = Pantry_Item(
            household_account_id=household_account_id,
            food_id=food_id,
            quantity=quantity,
            expiry_date=expiry_date,
            minimum_quantity=minimum_quantity,
            is_expired=is_expired
        )

        return repository.save(pantry_item)


@tool("remove_product")
def remove_product(
    pantry_item_id: int
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
    household_account_id: int
) -> list[Pantry_Item]:
    """
    Lista todo o estoque do usuário.

    Parâmetros:
        - household_account_id: Identificador da conta do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_stock(household_account_id)


@tool("get_expired_products")
def get_expired_products(
    household_account_id: int
) -> list[Pantry_Item]:
    """
    Lista produtos vencidos ou próximos do vencimento.

    Parâmetros:
        - household_account_id: Identificador da conta do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_expired_products(
            household_account_id
        )


@tool("get_missing_products")
def get_missing_products(
    household_account_id: int
):
    """
    Lista produtos cuja quantidade está abaixo do mínimo configurado.

    Parâmetros:
        - household_account_id: Identificador da conta do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_missing_products(
            household_account_id
        )


@tool("get_category_info")
def get_category_info(
    household_account_id: int
):
    """
    Retorna um relatório de produtos agrupados por categoria.

    Parâmetros:
        - household_account_id: Identificador da conta do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_category_info(
            household_account_id
        )


@tool("get_brand_info")
def get_brand_info(
    household_account_id: int
):
    """
    Retorna um relatório contendo a quantidade de produtos por marca.

    Parâmetros:
        - household_account_id: Identificador da conta do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_brand_info(
            household_account_id
        )
    

@tool("get_foods")
def get_foods() -> list[Food]:
    """
    Lista todos os alimentos cadastrados.

    Utilize esta ferramenta antes de adicionar um produto ao estoque
    quando for necessário descobrir qual é o food_id correspondente.

    Parâmetros:
        Nenhum.
    """

    with SessionLocal() as session:
        repository = FoodRepository(session)

        return repository.get_foods()