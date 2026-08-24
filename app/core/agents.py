from functools import lru_cache

from langchain.agents import create_agent

from .llms import get_fast_llm, get_specialist_llm


@lru_cache(maxsize=1)
def get_faq_agent():
    """Cria o agente de FAQ somente quando a rota for utilizada."""

    from ..tools.faq_tools import faq_retriever
    from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO

    return create_agent(
        model=get_fast_llm(),
        tools=[faq_retriever],
        system_prompt=FAQ_PROMPT_COMPLETO,
    )


@lru_cache(maxsize=1)
def get_recipe_agent():
    """Cria o agente de receitas somente quando a rota for utilizada."""

    from ..tools.mongo_recipe_tools import (
        buscar_receitas_usuario,
        salvar_receita,
    )
    from ..tools.pg_tools import get_expired_products, get_stock
    from .prompts.prompt_receitas import RECEITAS_PROMPT_COMPLETO

    return create_agent(
        model=get_specialist_llm(),
        tools=[
            buscar_receitas_usuario,
            salvar_receita,
            get_stock,
            get_expired_products,
        ],
        system_prompt=RECEITAS_PROMPT_COMPLETO,
    )


@lru_cache(maxsize=1)
def get_events_agent():
    """Cria o agente de eventos somente quando a rota for utilizada."""

    from ..tools.mongodb_tools import (
        add_event,
        cancel_event,
        get_events,
        postpone_event,
        update_description,
    )
    from .prompts.prompt_events import EVENTS_PROMPT_COMPLETO

    return create_agent(
        model=get_specialist_llm(),
        tools=[
            add_event,
            get_events,
            postpone_event,
            update_description,
            cancel_event,
        ],
        system_prompt=EVENTS_PROMPT_COMPLETO,
    )


@lru_cache(maxsize=1)
def get_stock_agent():
    """Cria o agente de estoque somente quando a rota for utilizada."""

    from ..tools.pg_tools import (
        add_product,
        get_brand_info,
        get_category_info,
        get_expired_products,
        get_foods,
        get_missing_products,
        get_stock,
        remove_product,
    )
    from .prompts.prompt_estoque import ESTOQUE_PROMPT_COMPLETO

    return create_agent(
        model=get_specialist_llm(),
        tools=[
            add_product,
            remove_product,
            get_stock,
            get_missing_products,
            get_expired_products,
            get_category_info,
            get_brand_info,
            get_foods,
        ],
        system_prompt=ESTOQUE_PROMPT_COMPLETO,
    )


__all__ = [
    "get_events_agent",
    "get_faq_agent",
    "get_recipe_agent",
    "get_stock_agent",
]