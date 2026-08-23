from datetime import date

from langchain.tools import tool

from ..repository.pgsql.config import SessionLocal
from ..model.pgsql.pantry_item import Pantry_Item
from ..model.pgsql.food import Food

from ..repository.pgsql.stock import StockRepository
from ..repository.pgsql.food import FoodRepository


@tool("add_product")
def add_product(
    profile_id: int,
    food_id: int,
    quantity: int,
    expiry_date: date,
) -> Pantry_Item | None:
    """
    Adiciona um produto ao estoque do usuário.

    Parâmetros:
        - profile_id: Id do perfil do usuário.
        - food_id: Id do alimento.
        - quantity: Quantidade disponível.
        - expiry_date: Data de vencimento.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        pantry_item = Pantry_Item(
            profile_id=profile_id,
            food_id=food_id,
            quantity=quantity,
            expiry_date=expiry_date,
        )

        return repository.save(pantry_item)


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
) -> list[Pantry_Item]:
    """
    Lista todo o estoque do usuário.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_stock(profile_id)


@tool("get_expired_products")
def get_expired_products(
    profile_id: int,
) -> list[Pantry_Item]:
    """
    Lista produtos vencidos ou próximos do vencimento.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_expired_products(
            profile_id
        )


@tool("get_missing_products")
def get_missing_products(
    profile_id: int,
):
    """
    Lista produtos cuja quantidade está abaixo do mínimo configurado.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_missing_products(
            profile_id
        )


@tool("get_category_info")
def get_category_info(
    profile_id: int,
):
    """
    Retorna um relatório de produtos agrupados por categoria.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_category_info(
            profile_id
        )


@tool("get_brand_info")
def get_brand_info(
    profile_id: int,
):
    """
    Retorna um relatório de produtos agrupados por marca.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        return repository.get_brand_info(
            profile_id
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