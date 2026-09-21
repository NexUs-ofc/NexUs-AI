from dotenv import load_dotenv
from langchain.agents import create_agent

from ..tools.faq_tools import faq_retriever
from ..tools.general_tools import recomendar_receita
from ..tools.mongo_recipe_tools import (
    buscar_receitas_usuario,
    salvar_receita,
)
from ..tools.mongodb_tools import (
    add_recipe,
    cancel_event,
    create_event,
    create_list,
    get_events,
    get_list,
    postpone_event,
    remove_recipe,
    update_description,
    update_list,
)
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
from .llms import fast_llm, specialist_llm
from .prompts.prompt_estoque import ESTOQUE_PROMPT_COMPLETO
from .prompts.prompt_events import EVENTS_PROMPT_COMPLETO
from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO
from .prompts.prompt_receitas import RECEITAS_PROMPT_COMPLETO

load_dotenv(".env")



faq_app = create_agent(
    model=fast_llm,
    tools=[
        faq_retriever,
    ],
    system_prompt=FAQ_PROMPT_COMPLETO,
)



recipe_app = create_agent(
    model=specialist_llm,
    tools=[
        buscar_receitas_usuario,
        salvar_receita,
        get_stock,
        get_expired_products,
    ],
    system_prompt=RECEITAS_PROMPT_COMPLETO,
)


events_app = create_agent(
    model=specialist_llm,
    tools=[
        create_event,
        get_events,
        postpone_event,
        update_description,
        cancel_event,
        recomendar_receita,
        add_recipe,
        remove_recipe,
        create_list,
        get_list,
        update_list,
    ],
    system_prompt=EVENTS_PROMPT_COMPLETO,
)



stock_app = create_agent(
    model=specialist_llm,
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