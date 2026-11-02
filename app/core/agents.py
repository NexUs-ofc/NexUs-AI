import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Thread
from typing import Literal

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError, create_model

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
    alterar_item_lista,
    cancel_event,
    create_event,
    create_list,
    get_events,
    get_list,
    postpone_event,
    remove_recipe,
    renomear_lista,
    update_description,
    update_list,
)
from ..tools.pg_tools import (
    get_brand_info,
    get_category_info,
    get_expired_products,
    get_missing_products,
    get_stock,
    remove_product,
)
from ..tools.preference_tools import consultar_preferencias
from ..tools.recipe_tools import ingredientes_para_comprar
from .llms import (
    estoque_llm,
    estoque_reserva,
    fast_llm,
    fast_reserva,
    specialist_llm,
    specialist_reserva,
)
from .prompts.prompt_estoque import ESTOQUE_PREAMBULO
from .prompts.prompt_events import EVENTS_PREAMBULO
from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO
from .prompts.prompt_receitas import RECEITAS_PREAMBULO
from .provider_policy import CallBudgetMiddleware, TransientModelFallback
from .skills import SKILLS

logger = logging.getLogger(__name__)

TAVILY_HABILITADAS = {"tavily_search"}
TAVILY_CARREGAMENTO_TIMEOUT_S = 5

OPERACOES_DE_ESCRITA = {
    "remove_product", "salvar_receita", "create_event", "postpone_event",
    "update_description", "cancel_event", "add_recipe", "remove_recipe",
    "create_list", "update_list", "alterar_item_lista", "renomear_lista",
}


def _reserva_do_modelo(reservas):
    """
    Se o modelo principal do agente falhar (timeout, 504, cota), a chamada e
    refeita no provedor de reserva. Sem reserva configurada, nada muda.
    """

    fallback = [TransientModelFallback(*reservas)] if reservas else []
    return [*fallback, CallBudgetMiddleware()]


async def _carregar_tavily():
    all_tools = await asyncio.wait_for(
        load_tavily_tools(), timeout=TAVILY_CARREGAMENTO_TIMEOUT_S,
    )
    return [_com_versao_sincrona(t) for t in all_tools if t.name in TAVILY_HABILITADAS]


def _com_versao_sincrona(tool):
    """
    A tool da Tavily vem so assincrona (MCP). O fluxo chama os agentes com
    invoke, que e sincrono, e sem versao sincrona a busca falha em toda chamada
    com "does not support sync invocation". A ponte roda a coroutine num loop
    proprio, numa thread a parte, como o carregamento faz.
    """

    if tool.func is not None or tool.coroutine is None:
        return tool

    assincrona = tool.coroutine

    def sincrona(**kwargs):
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, assincrona(**kwargs)).result()

    tool.func = sincrona
    return tool


def carregar_tavily_tools():
    resultado = Queue(maxsize=1)

    def carregar():
        try:
            resultado.put((True, asyncio.run(_carregar_tavily())))
        except Exception as error:  # noqa: BLE001 -- a busca externa e opcional.
            resultado.put((False, error))

    # Uma chamada MCP que ignora cancelamento nao pode manter vivo o processo
    # de reload do Uvicorn. A thread e daemon e o servidor segue sem busca web
    # quando a Tavily nao responde dentro do prazo.
    worker = Thread(target=carregar, name="tavily-tools-load", daemon=True)
    worker.start()
    worker.join(timeout=TAVILY_CARREGAMENTO_TIMEOUT_S + 1)
    if worker.is_alive():
        logger.warning(
            "Tempo limite ao carregar as ferramentas Tavily; o agente continuará sem busca na web."
        )
        return []

    try:
        sucesso, valor = resultado.get_nowait()
    except Empty:
        logger.warning("A Tavily terminou sem retornar ferramentas; busca web desabilitada.")
        return []
    if sucesso:
        return valor

    logger.error(
        "Não foi possível carregar as tools da Tavily; o agente de receitas segue sem busca na web.",
        exc_info=(type(valor), valor, valor.__traceback__),
    )
    return []


tavily_tools = carregar_tavily_tools()

faq_app = create_agent(
    model=fast_llm,
    middleware=_reserva_do_modelo(fast_reserva),
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
        ingredientes_para_comprar,
        remove_product,
        get_stock,
        get_missing_products,
        get_expired_products,
        get_category_info,
        get_brand_info,
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
        update_list,
        get_list,
        renomear_lista,
        alterar_item_lista,
        consultar_preferencias,
        buscar_historico,
        buscar_receitas_usuario,
        salvar_receita,
        *tavily_tools,
    )
}

_FERRAMENTAS_DE_ESCRITA_AUSENTES = OPERACOES_DE_ESCRITA - set(CATALOGO_FERRAMENTAS)
if _FERRAMENTAS_DE_ESCRITA_AUSENTES:
    raise RuntimeError(
        "Operações de escrita sem ferramenta registrada: "
        + ", ".join(sorted(_FERRAMENTAS_DE_ESCRITA_AUSENTES))
    )


def _schema_argumentos_operacao(nome: str):
    ferramenta = CATALOGO_FERRAMENTAS.get(nome)
    if ferramenta is None:
        raise ValueError(f"Operação sem ferramenta: {nome}")
    schema = ferramenta.args_schema
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise TypeError(f"A ferramenta {nome} precisa declarar um schema Pydantic.")
    if nome == "create_event":
        # A criação do evento aceita início/fim em texto e os normaliza para
        # `data`; preserve os dois campos na proposta tipada.
        schema = create_model(
            "PropostaCreateEventArguments",
            __base__=schema,
            inicio=(str | None, None),
            fim=(str | None, None),
        )
    return schema


def _montar_schema_adiamento(operacoes: set[str] | None = None):
    """Schema compacto, com operações permitidas específicas para cada skill."""
    nomes = tuple(sorted(operacoes or OPERACOES_DE_ESCRITA))
    ausentes = set(nomes) - OPERACOES_DE_ESCRITA
    if not nomes or ausentes:
        raise ValueError(f"Operações de adiamento inválidas: {sorted(ausentes)}")
    tipo_operacao = Literal.__getitem__(nomes)
    nome_modelo = "AdiamentoInput_" + "_".join(nomes)
    return create_model(
        nome_modelo,
        operacao=(tipo_operacao, Field(description="Operação autorizada por esta skill.")),
        argumentos=(dict[str, object], Field(description=(
            "Parâmetros da operação selecionada. Informe somente os campos exigidos "
            "pela ferramenta dessa operação."
        ))),
        justificativa=(str, Field(min_length=1, description="Pedido do usuário que justifica a operação.")),
    )


def _registrar_adiamento(operacao, argumentos, justificativa, schema, operacoes_permitidas):
    from ..auth import identidade

    try:
        proposta = schema.model_validate({
            "operacao": operacao,
            "argumentos": argumentos,
            "justificativa": justificativa,
        })
        if proposta.operacao not in operacoes_permitidas:
            return "FALHA: esta skill não pode propor essa operação."
        argumentos_tipados = _schema_argumentos_operacao(proposta.operacao).model_validate(
            proposta.argumentos,
        )
    except ValidationError as error:
        return f"FALHA: parâmetros inválidos para {operacao}: {error.errors(include_url=False)}"
    if not proposta.justificativa.strip():
        return "FALHA: informe por que esta operação atende ao pedido atual."
    return identidade.adiar_operacao(
        proposta.operacao, argumentos_tipados, proposta.justificativa,
    )


AdiamentoInput = _montar_schema_adiamento()


@tool("adiar_operacao", args_schema=AdiamentoInput)
def adiar_operacao_tool(operacao: str, argumentos: dict[str, object], justificativa: str) -> str:
    """Propõe uma operação; o juiz valida antes de qualquer gravação."""
    return _registrar_adiamento(
        operacao, argumentos, justificativa, AdiamentoInput, OPERACOES_DE_ESCRITA,
    )


def _criar_tool_adiamento(operacoes: set[str]):
    """Cria a única ferramenta de escrita da skill, limitada às operações dela."""
    schema = _montar_schema_adiamento(operacoes)

    def adiar(operacao: str, argumentos: dict[str, object], justificativa: str) -> str:
        """Propõe uma operação permitida nesta skill para validação do juiz."""
        return _registrar_adiamento(operacao, argumentos, justificativa, schema, operacoes)

    return tool("adiar_operacao", args_schema=schema)(adiar)

PREAMBULO_DO_AGENTE = {
    "receitas": RECEITAS_PREAMBULO,
    "eventos": EVENTS_PREAMBULO,
    "estoque": ESTOQUE_PREAMBULO,
}


def _ferramentas_da_skill(skill):
    faltando = [n for n in skill.ferramentas
                if n not in CATALOGO_FERRAMENTAS and n not in TAVILY_HABILITADAS]

    if faltando:
        logger.warning(
            "skill %s declara ferramenta inexistente: %s",
            skill.nome,
            ", ".join(faltando),
        )

    ferramentas = [CATALOGO_FERRAMENTAS[n] for n in skill.ferramentas
                   if n in CATALOGO_FERRAMENTAS and n not in OPERACOES_DE_ESCRITA]
    operacoes_da_skill = set(skill.ferramentas) & OPERACOES_DE_ESCRITA
    if operacoes_da_skill:
        ferramentas.append(_criar_tool_adiamento(operacoes_da_skill))
    return ferramentas


def _montar_agentes_das_skills():
    agentes = {}

    for nome, skill in SKILLS.items():
        preambulo = PREAMBULO_DO_AGENTE.get(skill.agente, "")

        agentes[nome] = create_agent(
            model=estoque_llm if skill.agente == "estoque" else specialist_llm,
            middleware=_reserva_do_modelo(
                estoque_reserva if skill.agente == "estoque" else specialist_reserva
            ),
            tools=_ferramentas_da_skill(skill),
            system_prompt=(skill.prompt(preambulo) +
                           "\n\nAUTORIZAÇÃO DE ESCRITAS: consultas continuam disponíveis. "
                           "Para qualquer alteração, use somente adiar_operacao e escolha uma "
                           "das operações permitidas nesta skill. Envie os campos diretos "
                           "{operacao, argumentos, justificativa}; argumentos contém somente "
                           "os parâmetros da ferramenta selecionada. Nunca proponha uma operação "
                           "de outra skill. "
                           "A mensagem de retorno é apenas um recibo de proposta, nunca confirmação "
                           "de sucesso. Em operações dependentes, use $op-N.campo para referenciar "
                           "o resultado de uma proposta anterior. Só afirme sucesso após receber "
                           "a evidência do executor."),
        )

    return agentes


AGENTES_DAS_SKILLS = _montar_agentes_das_skills()
