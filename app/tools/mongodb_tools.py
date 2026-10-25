import json
import re
import unicodedata
from datetime import datetime

from bson import ObjectId
from langchain.tools import tool

from ..auth import identidade
from ..model.mongodb.event import Event
from ..model.mongodb.recipe import Recipe
from ..model.mongodb.shopping_list import ShoppingList, normalize_item
from ..repository.mongodb.events import EventsRepository
from ..repository.mongodb.recipes import RecipesRepository
from ..repository.mongodb.shopping_lists import (
    ShoppingListsRepository,
    ShoppingListUnavailable,
)
from ..repository.pgsql.config import SessionLocal
from ..repository.pgsql.food import FoodRepository
from ..repository.pgsql.stock import StockRepository

events_repository = EventsRepository()


# O schema gerado a partir de `datetime` exige date-time completo, e o modelo
# escreve "2026-09-30" quando a pergunta e sobre um dia. O Groq recusa a
# chamada antes de ela chegar aqui, entao a data entra como texto e a conversao
# acontece neste lado.
_FORMATOS_DATA = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)


def _para_datetime(valor: str | None) -> datetime | None:
    """Converte a data recebida do modelo. Devolve None quando nao vem nada."""

    if valor is None or isinstance(valor, datetime):
        return valor

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        pass

    for formato in _FORMATOS_DATA:
        try:
            # Naive de proposito: e o que o resto do app grava no Mongo.
            return datetime.strptime(texto, formato)
        except ValueError:
            continue

    raise ValueError(
        f"Data '{texto}' nao reconhecida. Use o formato AAAA-MM-DD ou "
        f"AAAA-MM-DDTHH:MM."
    )


def _normalizar(nome: str) -> str:
    """Minusculo, sem acento e sem espaco nas pontas, para comparar nomes."""

    sem_acento = unicodedata.normalize("NFKD", nome or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))

    return " ".join(sem_acento.lower().split())


def _tem_no_estoque(nome: str, estoque: dict[str, float]) -> bool:
    """
    Ingrediente da receita casa com item do estoque pelo nome: igual, ou um
    comeca pelo outro seguido de espaco ("leite" e "leite integral").
    """

    alvo = _normalizar(nome)

    if not alvo:
        return False

    return any(
        quantidade > 0
        and (item == alvo or item.startswith(alvo + " ") or alvo.startswith(item + " "))
        for item, quantidade in estoque.items()
    )


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
    titulo: str,
    descricao: str,
    data: str,
    duracao: int,
    local: str,
    qtd_pessoas: int
) -> Event:
    """
    Insere um evento no banco de dados, campos obrigatórios:
        - titulo: Texto intuitivo sobre o evento;
        - descricao: Texto explicitando informações do evento, deve conter tipo do evento obrigatóriamente;
        - data: Data e hora do evento, no formato "AAAA-MM-DDTHH:MM";
        - duracao: Duração do evento em minutos;
        - local: Localização do evento;
        - qtd_pessoas: Total de participantes do evento;
    """
    household_id = identidade.perfil()


    evento = Event(
        household_id=household_id,
        title=titulo,
        description=descricao,
        date=_para_datetime(data),
        duration=duracao,
        local=local,
        qtd_people=qtd_pessoas,
    )

    return events_repository.create_event(event=evento)


@tool("get_events")
def get_events(
    inicio: str | None = None,
    fim: str | None = None,
    tipo: str | None = None,
    qtd_min: int | None = None,
    titulo_receitas: list[str] | None = None,
) -> str:
    """
    Busca eventos no banco de dados com base ou não nos seguintes filtros opcionais fornecidos:
        - inicio: Data mínima do intervalo, no formato "AAAA-MM-DD";
        - fim: Data máxima do intervalo, no formato "AAAA-MM-DD";
        - tipo: Tipo de evento que será validado na descrição (ex: Churrasco, festa, jantar, etc...);
        - qtd_min: Quantidade mínima de pessoas que evento deve ter;
        - titulo_receitas: Receitas que o evento deve ter;
    """
    household_id = identidade.perfil()


    eventos = events_repository.get_events(
        household_id=household_id,
        start=_para_datetime(inicio),
        end=_para_datetime(fim),
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
    new_date: str
) -> Event | None:
    """
    Adia um evento existente para uma nova data.

    Parâmetros:
        - event_id: Identificador do evento que será atualizado.
        - new_date: Nova data do evento, no formato "AAAA-MM-DDTHH:MM".
    """

    event = events_repository.get_event_by_id(event_id)

    if event is None:
        return None

    event.date = _para_datetime(new_date)

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
    titulo: str = "",
    porcoes: int = 0,
    ingredientes: list[dict] | None = None,
    recipe_id: str = "",
) -> Event | None:
    """
    Adiciona uma receita ao evento: escala os ingredientes para a quantidade
    de pessoas do evento, confere o estoque pelo nome e grava no evento.

    Use com a receita que recomend_recipe devolveu: passe titulo, porcoes e
    ingredientes. Ela ganha um id gerado aqui e NÃO entra nas receitas salvas
    do usuário. Para usar uma receita que ele já salvou, passe só recipe_id.

    Parâmetros:
        - event_id: Identificador do evento.
        - titulo: Título da receita.
        - porcoes: Para quantas pessoas estão as quantidades informadas.
        - ingredientes: [{"nome": str, "quantidade": str}], ex.:
          [{"nome": "Picanha", "quantidade": "2 kg"}].
        - recipe_id: Opcional. Id de uma receita salva, no lugar dos campos acima.
    """

    event = events_repository.get_event_by_id(event_id)

    if event is None or event.household_id != identidade.perfil():
        return None

    if recipe_id:
        recipe = RecipesRepository.get_recipe_by_id(recipe_id, account_id=identidade.conta())

        if recipe is None:
            return None
    else:
        if not titulo or not ingredientes:
            return None

        # Receita de evento nao vai para a collection de receitas: so as que
        # o usuario pede para salvar ficam la. O id e gerado para o evento
        # conseguir remover a receita depois (remove_recipe).
        recipe = Recipe(
            title=titulo,
            serving_size=porcoes or event.qtd_people,
            ingredients=[
                {
                    "name": str(
                        item.get("nome") or item.get("ingrediente") or item.get("name") or ""
                    ).strip(),
                    "required_quantity": str(
                        item.get("quantidade")
                        or item.get("quantidade_total")
                        or item.get("required_quantity")
                        or ""
                    ),
                }
                for item in ingredientes
                if isinstance(item, dict)
            ],
            instructions="",
            account_id=identidade.conta(),
            _id=ObjectId(),
        )

    ratio = event.qtd_people / recipe.serving_size if recipe.serving_size else 1

    with SessionLocal() as session:
        stock_repository = StockRepository(session)
        stock_items = stock_repository.get_stock(event.household_id)
        nomes = {food.id: food.name for food in FoodRepository(session).get_foods()}

    # Estoque por nome do alimento: a receita guarda o nome, nao o food_id.
    estoque: dict[str, float] = {}

    for item in stock_items:
        nome = _normalizar(nomes.get(item.food_id, ""))

        if nome:
            estoque[nome] = estoque.get(nome, 0) + (item.quantity or 0)

    scaled_ingredients = []

    for ingredient in recipe.ingredients:
        nome = str(ingredient.get("name") or ingredient.get("ingredient") or "").strip()

        scaled_ingredients.append({
            "ingredient": nome,
            "total_quantity": _scale_quantity(
                str(ingredient.get("required_quantity") or ""),
                ratio,
            ),
            "has_enough": _tem_no_estoque(nome, estoque),
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
def create_list(title: str, items: list[dict], event_id: str = "") -> str:
    """Cria uma lista de compras SOMENTE quando a pessoa pedir e confirmar os itens.
    title: título escolhido ou nome da receita/evento.
    items: [{"name": "Arroz", "quantity": 200, "unitOfMeasure": "g", "checked": false}].
      Também aceita ingredient/quantity/purchased com quantidade "200 g".
      Todos os itens precisam de nome, quantidade positiva e unidade.
    event_id: opcional; deixe vazio para compras avulsas ou de uma receita.
    Não salva receita, não cria evento e nunca inclui produtos no estoque.
    """
    household = identidade.perfil()
    if event_id:
        if not ObjectId.is_valid(event_id):
            return "FALHA: evento não encontrado. A lista não foi criada."
        event = events_repository.get_event_by_id(event_id)
        if event is None or event.household_id != household:
            return "FALHA: evento não encontrado. A lista não foi criada."
    try:
        if not items:
            raise ValueError("Informe os itens da lista antes de criar.")
        shopping = ShoppingList(household_id=household, title=title, items=items, event_id=event_id)
    except (ValueError, TypeError, ZeroDivisionError) as error:
        return f"FALHA: lista não criada. {error}"
    result = identidade.executar_gravacao(
        "create_list", {
            "title": shopping.title.casefold(),
            "items": [
                {"name": _normalizar(item["name"]), "quantity": float(item["quantity"]),
                 "unitOfMeasure": _normalizar(item["unitOfMeasure"]), "checked": item["checked"]}
                for item in shopping.items
            ],
            "event_id": shopping.event_id,
        },
        lambda: ShoppingListsRepository.create_list(shopping),
    )
    if result is None:
        return "FALHA: não foi possível criar a lista. Tente novamente."
    return json.dumps(result.to_dict(), ensure_ascii=False, default=str)


@tool("get_list")
def get_list(list_id: str = "", title: str = "") -> str:
    """Consulta listas da casa autenticada. Nunca peça identificador à pessoa.
    list_id: opcional, use um id já retornado pela consulta.
    title: opcional, busca por trecho do título, como "jantar". Sem filtros
      retorna até 20 listas recentes. Se houver mais de uma, pergunte qual.
    Retorna uma lista JSON, com id, título e todos os itens (array_list).
    """
    try:
        if list_id:
            found = ShoppingListsRepository.get_list(list_id, household_id=identidade.perfil())
            lists = [found] if found else []
        else:
            lists = ShoppingListsRepository.get_lists(identidade.perfil(), title=title)
    except ShoppingListUnavailable:
        return "FALHA: não foi possível consultar as listas. Isso não significa que não existam."
    return json.dumps([item.to_dict() for item in lists], ensure_ascii=False, default=str)


@tool("update_list")
def update_list(list_id: str, items: list[dict] | None = None, title: str | None = None) -> str:
    """Atualiza ou renomeia uma lista da casa após autorização da pessoa.
    list_id: id descoberto por get_list, nunca pedido ao usuário.
    items: conjunto COMPLETO de itens; mantenha os que não mudaram e seus ids.
      [{"id": "...", "name": "Arroz", "quantity": 200, "unitOfMeasure": "g", "checked": true}].
      Marcar comprado não remove o item. None preserva os itens; [] esvazia.
    title: opcional, novo título. None mantém o título.
    """
    household = identidade.perfil()
    try:
        existing = ShoppingListsRepository.get_list(list_id, household_id=household)
        if existing is None:
            return "FALHA: lista não encontrada."
        if items is None and title is None:
            return "FALHA: informe o que deseja alterar."
        new_title = title.strip() if title is not None else existing.title
        if not new_title:
            return "FALHA: o título não pode ficar vazio."
        new_items = existing.items
        if items is not None:
            new_items = []
            old_ids = {item["id"]: item for item in existing.items}
            for raw in items:
                item = normalize_item(raw)
                if raw.get("id") and item["id"] not in old_ids:
                    return "FALHA: um item não pertence a esta lista. Consulte novamente."
                matches = [old for old in existing.items
                           if _normalizar(old["name"]) == _normalizar(item["name"])
                           and _normalizar(old["unitOfMeasure"]) == _normalizar(item["unitOfMeasure"])]
                old = old_ids.get(raw.get("id"))
                if not old and not raw.get("id") and len(matches) > 1:
                    return "FALHA: há itens repetidos; consulte os ids antes de alterar."
                if not old and len(matches) == 1:
                    old = matches[0]
                if old:
                    item["id"] = old["id"]
                    if not any(key in raw for key in ("checked", "purchased", "comprado")):
                        item["checked"] = old["checked"]
                new_items.append(item)
            if len({item["id"] for item in new_items}) != len(new_items):
                return "FALHA: o mesmo item foi informado mais de uma vez."
        result = identidade.executar_gravacao(
            "update_list", {"list_id": list_id, "items": items, "title": title},
            lambda: ShoppingListsRepository.update_list(
                list_id, household_id=household, items=new_items, title=new_title,
            ),
        )
    except (ValueError, TypeError, ZeroDivisionError) as error:
        return f"FALHA: lista não alterada. {error}"
    except ShoppingListUnavailable:
        return "FALHA: não foi possível atualizar a lista. Consulte novamente."
    if result is None:
        return "FALHA: lista não atualizada. Consulte novamente."
    return json.dumps(result.to_dict(), ensure_ascii=False, default=str)
