import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.auth import identidade
from app.tools import (
    general_tools,
    memory_tools,
    mongo_recipe_tools,
    mongodb_tools,
    pg_tools,
    preference_tools,
)

IDS = {"profile_id", "account_id", "household_id", "household_account_id"}

TOOLS_COM_DONO = [
    pg_tools.add_product,
    pg_tools.get_stock,
    pg_tools.get_expired_products,
    pg_tools.get_missing_products,
    pg_tools.get_category_info,
    pg_tools.get_brand_info,
    general_tools.recomendar_receita,
    memory_tools.buscar_historico,
    preference_tools.consultar_preferencias,
    mongo_recipe_tools.buscar_receitas_usuario,
    mongo_recipe_tools.salvar_receita,
    mongodb_tools.create_event,
    mongodb_tools.get_events,
    mongodb_tools.create_list,
]


@pytest.mark.parametrize("ferramenta", TOOLS_COM_DONO, ids=lambda t: t.name)
def test_modelo_nao_ve_nenhum_id_de_dono(ferramenta):
    # Se o id aparecer no schema, o modelo volta a poder copiar o dos exemplos.
    assert IDS.isdisjoint(ferramenta.args)


@tool("quem_sou")
def quem_sou() -> str:
    """Devolve a casa e a conta da requisicao."""
    return f"{identidade.perfil()}/{identidade.conta()}"


def test_identidade_chega_na_tool_executada_pelo_langgraph():
    # O ToolNode roda as tools num executor proprio; e la que o contexto
    # precisa chegar, nao numa chamada direta.
    chamada = AIMessage(content="", tool_calls=[{"name": "quem_sou", "args": {}, "id": "1"}])

    grafo = StateGraph(MessagesState)
    grafo.add_node("tools", ToolNode([quem_sou]))
    grafo.add_edge(START, "tools")
    grafo.add_edge("tools", END)

    with identidade.da_requisicao(124, 124):
        saida = grafo.compile().invoke({"messages": [chamada]})

    assert saida["messages"][-1].content == "124/124"


def test_requisicoes_seguidas_nao_herdam_a_casa_anterior():
    with identidade.da_requisicao(124, 124):
        pass

    with pytest.raises(identidade.SemIdentidade):
        identidade.perfil()


def test_remove_product_nao_apaga_item_de_outra_casa(monkeypatch):
    class Item:
        profile_id = 1

    class Repo:
        def __init__(self, _sessao):
            pass

        def find_by_id(self, _id):
            return Item()

        def remove_product(self, _item):
            raise AssertionError("apagou item de outra casa")

    class Sessao:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(pg_tools, "StockRepository", Repo)
    monkeypatch.setattr(pg_tools, "SessionLocal", Sessao)

    with identidade.da_requisicao(124, 124):
        assert pg_tools.remove_product.invoke({"pantry_item_id": 23}) is False
