from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.controller.config import logging
from app.core.agents import (
    events_app,
    faq_app,
    recipe_app,
    stock_app,
)
from app.core.llms import fast_llm
from app.core.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO
from app.guardrails.guardrails import (
    anonimizar,
    checar_entrada,
    checar_saida,
)
from app.observability.cost import estimate_cost_usd, extrair_tokens
from app.observability.tool_logging_callback import ToolLoggingCallback
from app.observability.tracing import generate_trace_id, span
from app.repository.mongodb.conversations import ConversationsRepository
from app.repository.mongodb.metrics import MetricsRepository
from app.repository.mongodb.tool_metrics import ToolMetricsRepository

from .state import State

logger = logging.getLogger(__name__)



def guardrail_entrada(state: State) -> State:
    with span(state["trace_id"], "guardrail_entrada"):
        texto_anonimizado, mapa = anonimizar(state["mensagem"])

        state["mensagem"] = texto_anonimizado
        state["mapa_pii"] = mapa

        resultado = checar_entrada(texto_anonimizado)

        if resultado["bloqueado"]:
            state["entrada_aprovada"] = False
            state["resposta_agente"] = resultado["mensagem"]
        else:
            state["entrada_aprovada"] = True

        logger.info(
            "guardrail_entrada avaliado",
            extra={
                "trace_id": state["trace_id"],
                "stage": "input",
                "mensagem_anonimizada": texto_anonimizado,
                "entrada_aprovada": state["entrada_aprovada"],
            },
        )

    return state



def roteador(state: State) -> State:
    with span(state["trace_id"], "roteador"):
        historico = state.get("historico", [])

        mensagem_usuario = (
            f"Histórico: {historico}\n"
            f"Mensagem: \"{state['mensagem']}\""
        )

        resposta = fast_llm.invoke([
            SystemMessage(content=ROTEADOR_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        state["rota"] = resposta.content.strip().lower()

        input_tokens, output_tokens = extrair_tokens(resposta)
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "roteador decidiu rota",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem_usuario,
                "rota": state["rota"],
            },
        )

    return state



def _invocar_agente(
    agent,
    mensagem: str,
    historico: list,
    trace_id: str,
) -> tuple[str, int, int]:
    """
    Invoca um agente e extrai sua resposta final.
    """

    messages = []

    for msg in historico:
        if msg["role"] == "user":
            messages.append(
                HumanMessage(content=msg["content"])
            )
        elif msg["role"] == "assistant":
            messages.append(
                AIMessage(content=msg["content"])
            )

    messages.append(
        HumanMessage(content=mensagem)
    )

    resultado = agent.invoke(
        {"messages": messages},
        config={
            "callbacks": [ToolLoggingCallback()],
            "metadata": {"trace_id": trace_id},
        },
    )

    mensagens_saida = resultado.get("messages", [])

    input_tokens = 0
    output_tokens = 0

    for msg in mensagens_saida:
        tokens_in, tokens_out = extrair_tokens(msg)
        input_tokens += tokens_in
        output_tokens += tokens_out

    if mensagens_saida:
        return mensagens_saida[-1].content, input_tokens, output_tokens

    return "", input_tokens, output_tokens



def agente_faq(state: State) -> State:
    with span(state["trace_id"], "faq"):
        historico = state.get("historico", [])

        mensagem = (
            f"ROUTE=faq\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}"
        )

        resposta_agente, input_tokens, output_tokens = _invocar_agente(
            faq_app,
            mensagem,
            historico,
            state["trace_id"],
        )
        state["resposta_agente"] = resposta_agente
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_faq respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state



def agente_receitas(state: State) -> State:
    with span(state["trace_id"], "receitas"):
        historico = state.get("historico", [])

        household_id = state.get(
            "household_account_id",
            0,
        )

        account_id = state.get(
            "account_id",
            0,
        )

        mensagem = (
            f"ROUTE=receitas\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"PROFILE_ID={household_id}\n"
            f"ACCOUNT_ID={account_id}"
        )

        resposta_agente, input_tokens, output_tokens = _invocar_agente(
            recipe_app,
            mensagem,
            historico,
            state["trace_id"],
        )
        state["resposta_agente"] = resposta_agente
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_receitas respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




def agente_estoque(state: State) -> State:
    with span(state["trace_id"], "estoque"):
        historico = state.get("historico", [])

        household_id = state.get(
            "household_account_id",
            0,
        )

        mensagem = (
            f"ROUTE=stock\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"PROFILE_ID={household_id}"
        )

        resposta_agente, input_tokens, output_tokens = _invocar_agente(
            stock_app,
            mensagem,
            historico,
            state["trace_id"],
        )
        state["resposta_agente"] = resposta_agente
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_estoque respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




def agente_eventos(state: State) -> State:
    with span(state["trace_id"], "eventos"):
        historico = state.get("historico", [])

        household_id = state.get(
            "household_account_id",
            0,
        )

        account_id = state.get(
            "account_id",
            0,
        )

        mensagem = (
            f"ROUTE=events\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"HOUSEHOLD_ID={household_id}\n"
            f"PROFILE_ID={household_id}\n"
            f"ACCOUNT_ID={account_id}"
        )

        resposta_agente, input_tokens, output_tokens = _invocar_agente(
            events_app,
            mensagem,
            historico,
            state["trace_id"],
        )
        state["resposta_agente"] = resposta_agente
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_eventos respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




def orquestrador(state: State) -> State:
    with span(state["trace_id"], "orquestrador"):
        resposta_agente = state.get(
            "resposta_agente",
            "",
        )

        rota = state.get(
            "rota",
            "fallback",
        )

        mensagem_usuario = (
            f"Rota: {rota}\n"
            f"Resposta do agente: \"{resposta_agente}\""
        )

        resposta = fast_llm.invoke([
            SystemMessage(content=ORQUESTRADOR_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        state["resposta_final"] = resposta.content.strip()

        input_tokens, output_tokens = extrair_tokens(resposta)
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "orquestrador finalizou resposta",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem_usuario,
                "resposta_final": state["resposta_final"],
            },
        )

    return state



def guardrail_saida(state: State) -> State:
    with span(state["trace_id"], "guardrail_saida"):
        mapa = state.get(
            "mapa_pii",
            {},
        )

        resultado = checar_saida(
            state["resposta_final"],
            mapa,
        )

        state["resposta_final"] = resultado["conteudo"]
        state["saida_aprovada"] = True

    return state



def decidir_pos_guardrail_entrada(state: State) -> str:
    if not state["entrada_aprovada"]:
        return "orquestrador"

    return "roteador"


def decidir_rota(state: State) -> str:
    return state["rota"]


def decidir_pos_guardrail_saida(state: State) -> str:
    if not state["saida_aprovada"]:
        return "orquestrador"

    return END



def executar_chat(
    mensagem: str,
    session_id: str | None,
    household_account_id: int,
    account_id: int,
) -> dict:
    """
    Função pública que encapsula a execução do workflow.
    """

    trace_id = generate_trace_id()

    if session_id and ConversationsRepository.sessao_ativa(session_id):
        historico = ConversationsRepository.get_historico(
            session_id
        )
    else:
        session_id = ConversationsRepository.create_session(
            account_id
        )

        historico = []

    started_at = datetime.now(timezone.utc)
    resultado = None
    erro = False

    try:
        resultado = ceris_workflow.invoke({
            "mensagem": mensagem,
            "historico": historico,
            "rota": "fallback",
            "resposta_agente": "",
            "resposta_final": "",
            "entrada_aprovada": False,
            "saida_aprovada": False,
            "mapa_pii": {},
            "household_account_id": household_account_id,
            "account_id": account_id,
            "trace_id": trace_id,
            "input_tokens": 0,
            "output_tokens": 0,
        })
    except Exception:
        erro = True

        logger.exception(
            "Falha ao executar workflow",
            extra={"trace_id": trace_id, "stage": "workflow"},
        )

        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        if resultado is not None and not resultado.get("entrada_aprovada", True):
            erro = True

        tool_calls = ToolMetricsRepository.count_by_trace_id(trace_id)

        input_tokens = resultado.get("input_tokens", 0) if resultado is not None else 0
        output_tokens = resultado.get("output_tokens", 0) if resultado is not None else 0

        MetricsRepository.save_request_metric(
            trace_id=trace_id,
            route=resultado.get("rota", "fallback") if resultado is not None else "fallback",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            error=erro,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost_usd(input_tokens, output_tokens),
        )

    resposta = resultado["resposta_final"]

    ConversationsRepository.append_messages(
        session_id,
        mensagem,
        resposta,
    )

    return {
        "resposta": resposta,
        "session_id": session_id,
    }


graph = StateGraph(State)

graph.add_node(
    "guardrail_entrada",
    guardrail_entrada,
)

graph.add_node(
    "roteador",
    roteador,
)

graph.add_node(
    "faq",
    agente_faq,
)

graph.add_node(
    "receitas",
    agente_receitas,
)

graph.add_node(
    "estoque",
    agente_estoque,
)

graph.add_node(
    "eventos",
    agente_eventos,
)

graph.add_node(
    "orquestrador",
    orquestrador,
)

graph.add_node(
    "guardrail_saida",
    guardrail_saida,
)



graph.set_entry_point(
    "guardrail_entrada"
)




graph.add_conditional_edges(
    "guardrail_entrada",
    decidir_pos_guardrail_entrada,
    {
        "roteador": "roteador",
        "orquestrador": "orquestrador",
    },
)



graph.add_conditional_edges(
    "roteador",
    decidir_rota,
    {
        "faq": "faq",
        "receitas": "receitas",
        "estoque": "estoque",
        "eventos": "eventos",
        "fallback": "orquestrador",
    },
)



graph.add_edge(
    "faq",
    "orquestrador",
)

graph.add_edge(
    "receitas",
    "orquestrador",
)

graph.add_edge(
    "estoque",
    "orquestrador",
)

graph.add_edge(
    "eventos",
    "orquestrador",
)




graph.add_edge(
    "orquestrador",
    "guardrail_saida",
)



graph.add_conditional_edges(
    "guardrail_saida",
    decidir_pos_guardrail_saida,
    {
        "orquestrador": "orquestrador",
        END: END,
    },
)


ceris_workflow = graph.compile()