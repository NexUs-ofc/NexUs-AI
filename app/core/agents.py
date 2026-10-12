import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from langchain.agents import create_agent

from ..tools.calc_tools import (
    calcular_percentual,
    escalar_quantidades,
    somar_valores,
)
from ..tools.date_tools import resolver_data
from ..tools.faq_tools import faq_retriever
from ..tools.general_tools import recomendar_receita
from ..tools.mcp.tavily_mcp import load_tavily_tools
from ..tools.memory_tools import buscar_historico
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
    resolver_alimento,
)
from ..tools.preference_tools import consultar_preferencias
from .llms import fast_llm, specialist_llm
from .prompts.prompt_estoque import ESTOQUE_PREAMBULO
from .prompts.prompt_events import EVENTS_PREAMBULO
from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO
from .prompts.prompt_receitas import RECEITAS_PREAMBULO
from .skills import SKILLS

logger = logging.getLogger(__name__)

TAVILY_HABILITADAS = {"tavily_search"}


async def _carregar_tavily():
   
    all_tools = await load_tavily_tools()
    return [t for t in all_tools if t.name in TAVILY_HABILITADAS]


def carregar_tavily_tools():
    
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        tem_loop = False
    else:
        tem_loop = True

    try:
        if not tem_loop:
            return asyncio.run(_carregar_tavily())

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, _carregar_tavily()).result()
    except Exception:
        logger.exception(
            "Não foi possível carregar as tools da Tavily; "
            "o agente de receitas segue sem busca na web."
        )
        return []


tavily_tools = carregar_tavily_tools()

faq_app = create_agent(
    model=fast_llm,
    tools=[
        faq_retriever,
    ],
    system_prompt=FAQ_PROMPT_COMPLETO,
)








# Um agente por skill, montado no import.
#
# Cada um recebe o prompt da sua skill e SO as ferramentas que ela declara. E o
# que faz o pedido pagar ~1800 tokens em vez de ~3600, e o modelo percorrer 3 a
# 7 ferramentas em vez de 12 a 15 a cada passo do loop.
#
# O preambulo do dominio vem do prompt_<dominio>: e o que diz quem o agente e e
# ate onde ele vai, igual para todas as skills daquele agente.

CATALOGO_FERRAMENTAS = {
    f.name: f
    for f in (
        resolver_data,
        resolver_alimento,
        add_product,
        remove_product,
        get_stock,
        get_missing_products,
        get_expired_products,
        get_category_info,
        get_brand_info,
        get_foods,
        somar_valores,
        escalar_quantidades,
        calcular_percentual,
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
        consultar_preferencias,
        buscar_historico,
        buscar_receitas_usuario,
        salvar_receita,
        *tavily_tools,
    )
}

PREAMBULO_DO_AGENTE = {
    "receitas": RECEITAS_PREAMBULO,
    "eventos": EVENTS_PREAMBULO,
    "estoque": ESTOQUE_PREAMBULO,
}


def _ferramentas_da_skill(skill):
    faltando = [n for n in skill.ferramentas if n not in CATALOGO_FERRAMENTAS]

    if faltando:
        logger.warning(
            "skill %s declara ferramenta inexistente: %s",
            skill.nome,
            ", ".join(faltando),
        )

    return [CATALOGO_FERRAMENTAS[n] for n in skill.ferramentas if n in CATALOGO_FERRAMENTAS]


def _montar_agentes_das_skills():
    agentes = {}

    for nome, skill in SKILLS.items():
        preambulo = PREAMBULO_DO_AGENTE.get(skill.agente, "")

        agentes[nome] = create_agent(
            model=specialist_llm,
            tools=_ferramentas_da_skill(skill),
            system_prompt=skill.prompt(preambulo),
        )

    return agentes


AGENTES_DAS_SKILLS = _montar_agentes_das_skills()
