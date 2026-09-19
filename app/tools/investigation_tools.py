import json

from langchain.tools import tool

from ..model.pgsql.food import Food
from ..model.pgsql.pantry_item import Pantry_Item
from ..repository.mongodb.events import EventsRepository
from ..repository.mongodb.recipes import RecipesRepository
from ..repository.pgsql.config import SessionLocal
from ..repository.pgsql.food import FoodRepository
from ..repository.pgsql.stock import StockRepository
from ..repository.qdrant.faq_repository import FAQRepository

faq_repo = FAQRepository()


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


def _estoque_para_json(profile_id: int, mensagem_vazio: str) -> str:
    with SessionLocal() as session:
        repository = StockRepository(session)

        itens = repository.get_stock(profile_id)
        foods = _food_lookup(session)

        if not itens:
            return mensagem_vazio

        return json.dumps(
            [_pantry_item_to_dict(item, foods) for item in itens],
            ensure_ascii=False,
            default=str,
        )


@tool("verificar_faq")
def verificar_faq(topico: str) -> str:
    """
    Verifica afirmações sobre funcionalidades, regras, políticas e termos
    do Ceris.AI consultando a base de conhecimento (FAQ).

    Parâmetros:
        - topico: Tema da afirmação a ser verificada.
    """

    respostas = faq_repo.buscar_respostas_faq(topico)

    if not respostas:
        return "Nenhum registro encontrado no FAQ para esse tópico."

    return "\n".join(f"- {resp}" for resp in respostas)


@tool("verificar_estoque")
def verificar_estoque(profile_id: int) -> str:
    """
    Verifica afirmações sobre itens e quantidades do estoque do usuário.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    return _estoque_para_json(
        profile_id,
        "O usuário não possui nenhum produto cadastrado no estoque.",
    )


@tool("verificar_produtos_vencidos")
def verificar_produtos_vencidos(profile_id: int) -> str:
    """
    Verifica afirmações sobre produtos vencidos ou próximos do vencimento.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        itens = repository.get_expired_products(profile_id)
        foods = _food_lookup(session)

        if not itens:
            return "Não há produtos vencidos ou próximos do vencimento."

        return json.dumps(
            [_pantry_item_to_dict(item, foods) for item in itens],
            ensure_ascii=False,
            default=str,
        )


@tool("verificar_produtos_em_falta")
def verificar_produtos_em_falta(profile_id: int) -> str:
    """
    Verifica afirmações sobre produtos em falta no estoque.

    Parâmetros:
        - profile_id: Identificador do perfil do usuário.
    """

    with SessionLocal() as session:
        repository = StockRepository(session)

        rows = repository.get_missing_products(profile_id)
        foods = _food_lookup(session)

        if not rows:
            return "Não há produtos em falta no momento."

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

        return json.dumps(data, ensure_ascii=False, default=str)


@tool("verificar_eventos")
def verificar_eventos(household_id: int) -> str:
    """
    Verifica afirmações sobre eventos da casa.

    Parâmetros:
        - household_id: Identificador da conta/casa dona dos eventos.
    """

    eventos = EventsRepository.get_events(household_id=household_id)

    if not eventos:
        return "Nenhum evento encontrado para essa casa."

    return json.dumps(
        [
            {**evento.to_dict(), "_id": str(evento.id)}
            for evento in eventos
        ],
        ensure_ascii=False,
        default=str,
    )


@tool("verificar_receitas_usuario")
def verificar_receitas_usuario(account_id: int) -> str:
    """
    Verifica afirmações sobre receitas salvas do usuário.

    Parâmetros:
        - account_id: Identificador da conta do usuário.
    """

    receitas = RecipesRepository.get_user_recipes(account_id)

    if not receitas:
        return "Nenhuma receita salva para este usuário."

    linhas = []
    for receita in receitas:
        curtida = "Sim" if receita.is_liked else "Não"
        linhas.append(
            f"- {receita.title} | Serve: {receita.serving_size} pessoas "
            f"| Ingredientes: {receita.ingredients} | Curtida: {curtida}"
        )

    return "\n".join(linhas)


@tool("verificar_alimentos")
def verificar_alimentos() -> str:
    """
    Verifica afirmações sobre o catálogo de alimentos cadastrados.

    Parâmetros:
        Nenhum.
    """

    with SessionLocal() as session:
        repository = FoodRepository(session)

        foods = repository.get_foods()

        if not foods:
            return "Nenhum alimento cadastrado no sistema."

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

        return json.dumps(data, ensure_ascii=False, default=str)