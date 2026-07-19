from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from .llms import fast_llm, specialist_llm
from ..tools.faq_tools import faq_retriever
from ..tools.mongodb_tools import (
    add_event,
    get_events,
    postpone_event,
    update_description,
    cancel_event
)
from ..tools.pg_tools import (
    add_product,
    remove_product,
    get_stock,
    get_missing_products,
    get_expired_products,
    get_category_info,
    get_brand_info
)
from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO
from .prompts.prompt_events import EVENTS_PROMPT_COMPLETO
from .prompts.prompt_estoque import ESTOQUE_PROMPT_COMPLETO

load_dotenv('.env')


faq_app = create_agent(
    model=fast_llm,
    tools=[faq_retriever],
    system_prompt=FAQ_PROMPT_COMPLETO,
)

events_app = create_agent(
    model=specialist_llm,
    tools=[
            add_event,
            get_events,
            postpone_event,
            update_description,
            cancel_event,
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
        get_brand_info
    ],
    system_prompt=ESTOQUE_PROMPT_COMPLETO
)