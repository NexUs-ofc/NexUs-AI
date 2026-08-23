import json
import re
from langchain.tools import tool
from datetime import datetime

from ..model.mongodb.event import Event
from ..model.mongodb.shopping_list import ShoppingList
from ..repository.mongodb.events import EventsRepository
from ..repository.mongodb.recipes import RecipesRepository
from ..repository.mongodb.shopping_lists import ShoppingListsRepository
from ..repository.pgsql.config import SessionLocal
from ..repository.pgsql.stock import StockRepository

events_repository = EventsRepository()


def _scale_quantity(quantity: str, ratio: float) -> str:
    match = re.match(r"^([\d.,]+)\s*(.*)$", quantity.strip())

    if not match:
        return quantity

    number = float(match.group(1).replace(",", "."))
    suffix = match.group(2).strip()
    scaled = number * ratio

    if scaled == int(scaled):
        scaled_str = str(int(scaled))
    else:
        scaled_str = f"{scaled:.2f}".rstrip("0").rstrip(".")

    return f"{scaled_str} {suffix}".strip()


@tool("create_event")
def create_event(
    household_id: int,
    titulo: str,
    descricao: str,
    data: datetime,
    duracao: int,
    local: str,
    qtd_pessoas: int
) -> Event:
    """
    Insere um evento no banco de dados, campos obrigatórios:
        - household_id: Identificador da conta/casa dona do evento;
        - titulo: Texto intuitivo sobre o evento;
        - descricao: Texto explicitando informações do evento, deve conter tipo do evento obrigatóriamente;
        - data: Data do evento em Datetime;
        - duracao: Duração do evento em minutos;
        - local: Localização do evento;
        - qtd_pessoas: Total de participantes do evento;
    """

    evento = Event(
        household_id=household_id,
        title=titulo,
        description=descricao,
        date=data,
        duration=duracao,
        local=local,
        qtd_people=qtd_pessoas,
    )

    return events_repository.create_event(event=evento)


@tool("get_events")
def get_events(
    household_id: int,
    inicio: datetime = None,
    fim: datetime = None,
    tipo: str = None,
    qtd_min: int = None,
    titulo_receitas: list[str] = None,
) -> str:
    """
    Busca eventos no banco de dados com base ou não nos seguintes filtros opcionais fornecidos:
        - household_id: Identificador da conta/casa dona dos eventos (obrigatório);
        - inicio: Data mínima de intervalo que evento pode estar;
        - fim: Data máxima de intervalo que evento pode estar;
        - tipo: Tipo de evento que será validado na descrição (ex: Churrasco, festa, jantar, etc...);
        - qtd_min: Quantidade mínima de pessoas que evento deve ter;
        - titulo_receitas: Receitas que o evento deve ter;
    """

    eventos = events_repository.get_events(
        household_id=household_id,
        start=inicio,
        end=fim,
        type=tipo,
        qtd_min=qtd_min,
        recipes_titles=titulo_receitas
    )

    if not eventos:
        return "Nenhum evento encontrado com os filtros informados."

    return json.dumps(
        [
            {**evento.to_dict(), "_id": str(evento.id)}
            for evento in eventos
        ],
        ensure_ascii=False,
        default=str,
    )


@tool("postpone_event")
def postpone_event(
    event_id: str,
    new_date: datetime
) -> Event | None:
    """
    Adia um evento existente para uma nova data.

    Parâmetros:
        - event_id: Identificador do evento que será atualizado.
        - new_date: Nova data do evento.
    """

    event = events_repository.get_event_by_id(event_id)

    if event is None:
        return None

    event.date = new_date

    return events_repository.update_event(event)


@tool("update_description")
def update_description(
    event_id: str,
    new_description: str
) -> Event | None:
    """
    Atualiza a descrição de um evento existente.

    Parâmetros:
        - event_id: Identificador do evento que será atualizado.
        - new_description: Nova descrição do evento.
    """

    event = events_repository.get_event_by_id(event_id)

    if event is None:
        return None

    event.description = new_description

    return events_repository.update_event(event)


@tool("cancel_event")
def cancel_event(
    event_id: str
) -> bool:
    """
    Remove definitivamente um evento do banco de dados.

    Parâmetros:
        - event_id: Identificador do evento que será cancelado.
    """

    return events_repository.delete_event(event_id)


@tool("add_recipe")
def add_recipe(
    event_id: str,
    recipe_id: str,
) -> Event | None:
    """
    Escala os ingredientes de uma receita pela quantidade de pessoas do
    evento (regra de três a partir do serving_size da receita), confere o
    estoque do usuário e adiciona a receita já escalada ao evento.

    Parâmetros:
        - event_id: Identificador do evento.
        - recipe_id: Identificador da receita já confirmada pelo usuário.
    """

    event = events_repository.get_event_by_id(event_id)

    if event is None:
        return None

    recipe = RecipesRepository.get_recipe_by_id(recipe_id)

    if recipe is None:
        return None

    ratio = event.qtd_people / recipe.serving_size

    with SessionLocal() as session:
        stock_repository = StockRepository(session)
        stock_items = stock_repository.get_stock(event.household_id)

    stock_by_food = {item.food_id: item.quantity for item in stock_items}

    scaled_ingredients = []

    for ingredient in recipe.ingredients:
        food_id = ingredient["food_id"]
        available = stock_by_food.get(food_id)

        scaled_ingredients.append({
            "food_id": food_id,
            "ingredient": f"food_{food_id}",
            "total_quantity": _scale_quantity(
                ingredient["required_quantity"],
                ratio,
            ),
            "has_enough": available is not None and available > 0,
        })

    recipe_entry = {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "ingredients": scaled_ingredients,
    }

    added = events_repository.add_recipe_to_event(event_id, recipe_entry)

    if not added:
        return None

    return events_repository.get_event_by_id(event_id)


@tool("remove_recipe")
def remove_recipe(
    event_id: str,
    recipe_id: str,
) -> Event | None:
    """
    Remove uma receita já vinculada de um evento.

    Parâmetros:
        - event_id: Identificador do evento.
        - recipe_id: Identificador da receita a remover.
    """

    removed = events_repository.remove_recipe_from_event(event_id, recipe_id)

    if not removed:
        return None

    return events_repository.get_event_by_id(event_id)


@tool("create_list")
def create_list(
    event_id: str,
    household_id: int,
    title: str,
    items: list[dict],
) -> ShoppingList | None:
    """
    Cria uma lista de compras vinculada (ou não) a um evento.

    Parâmetros:
        - event_id: Identificador do evento relacionado (pode ser vazio).
        - household_id: Identificador da conta/casa dona da lista.
        - title: Título da lista de compras.
        - items: Lista de itens no formato [{"food_id": int, "ingredient": str, "quantity": str, "purchased": bool}].
    """

    shopping_list = ShoppingList(
        household_id=household_id,
        title=title,
        items=items,
        event_id=event_id if event_id else None,
    )

    return ShoppingListsRepository.create_list(shopping_list)


@tool("get_list")
def get_list(
    list_id: str,
) -> ShoppingList | None:
    """
    Consulta uma lista de compras pelo identificador.

    Parâmetros:
        - list_id: Identificador da lista de compras.
    """

    return ShoppingListsRepository.get_list(list_id)


@tool("update_list")
def update_list(
    list_id: str,
    items: list[dict],
) -> ShoppingList | None:
    """
    Atualiza os itens de uma lista de compras existente.

    Parâmetros:
        - list_id: Identificador da lista de compras.
        - items: Novo conjunto de itens no formato [{"food_id": int, "ingredient": str, "quantity": str, "purchased": bool}].
    """

    return ShoppingListsRepository.update_list(list_id, items)