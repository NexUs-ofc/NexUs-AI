import re
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langsmith import trace, traceable

from app.controller.config import logging
from app.core.agents import (
    events_app,
    faq_app,
    recipe_app,
    stock_app,
)
from app.core.llms import fast_llm
from app.core.prompts.prompt_juiz import JUIZ_PROMPT_COMPLETO
from app.core.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO
from app.guardrails.guardrails import (
    PII,
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

LIMITE_DEVOLUCOES = 2
LIMITE_EVIDENCIA = 400
LIMITE_EVIDENCIAS_TOTAL = 2000
TURNOS_PARA_O_JUIZ = 4
TURNOS_PARA_O_AGENTE = 10

# As rotas que o grafo sabe atender. Qualquer outra coisa vira fallback.
ROTAS = ("faq", "receitas", "estoque", "eventos", "fallback")


def _mascarar(valor):
    """
    Devolve uma copia do valor com PII mascarada, para o que sai no trace.

    Nunca altera o objeto recebido: o State segue intacto para o grafo.
    """

    if isinstance(valor, str):
        for tipo, padrao in PII:
            valor = re.sub(padrao, f"[{tipo}_MASCARADO]", valor)

        return valor

    if isinstance(valor, dict):
        return {
            chave: _mascarar(item)
            for chave, item in valor.items()
            if chave != "mapa_pii"
        }

    if isinstance(valor, (list, tuple)):
        return [_mascarar(item) for item in valor]

    return valor


def _entrada_do_no(inputs: dict) -> dict:
    return {"state": _mascarar(inputs.get("state", {}))}


def _saida_do_no(outputs):
    return _mascarar(outputs)


_TRACE_NO = {
    "run_type": "chain",
    "process_inputs": _entrada_do_no,
    "process_outputs": _saida_do_no,
}


@traceable(name="guardrail_entrada", **_TRACE_NO)
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



@traceable(name="roteador", **_TRACE_NO)
def roteador(state: State) -> State:
    with span(state["trace_id"], "roteador"):
        historico = state.get("historico", [])

        mensagem_usuario = (
            f"Histórico: {_ultimos_turnos(historico, TURNOS_PARA_O_JUIZ)}\n"
            f"Mensagem: \"{state['mensagem']}\""
        )

        resposta = fast_llm.invoke([
            SystemMessage(content=ROTEADOR_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        state["rota"] = _normalizar_rota(resposta.content)

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



def _normalizar_rota(bruto: str) -> str:
    """
    Converte a saída do roteador numa rota que o grafo atende.

    O valor ia cru para o add_conditional_edges, então qualquer coisa fora
    da lista — "Rota: estoque", "estoque.", texto vazio — derrubava a
    requisição inteira com erro de grafo, e não com uma resposta ruim.
    """

    texto = (bruto or "").strip().lower()

    if texto in ROTAS:
        return texto

    for rota in ROTAS:
        if rota in texto:
            return rota

    logger.warning(
        "roteador devolveu rota desconhecida; caindo em fallback",
        extra={"stage": "roteador", "bruto": texto[:120]},
    )

    return "fallback"


def _ultimos_turnos(historico: list[dict], quantos: int) -> list[dict]:
    """
    Recorta o histórico antes de ele entrar num prompt.

    Sem teto, uma conversa longa cresce sem limite dentro de cada chamada:
    estoura o contexto do modelo e queima cota por mensagem.
    """

    if not historico:
        return []

    return historico[-quantos:]


def _invocar_agente(
    agent,
    mensagem: str,
    historico: list,
    trace_id: str,
    revisao: str = "",
) -> tuple[str, int, int, list[dict]]:
    """
    Invoca um agente e extrai sua resposta final, os tokens e o que as
    ferramentas devolveram.

    Quando o juiz devolveu a rodada anterior, o motivo entra na mensagem como
    REVISAO: é a unica diferenca entre a primeira tentativa e as seguintes.
    """

    if revisao:
        mensagem = f"{mensagem}\nREVISAO={revisao}"

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
    evidencias = []

    for msg in mensagens_saida:
        tokens_in, tokens_out = extrair_tokens(msg)
        input_tokens += tokens_in
        output_tokens += tokens_out

        if getattr(msg, "type", "") == "tool":
            evidencias.append({
                "ferramenta": getattr(msg, "name", "") or "ferramenta",
                "conteudo": msg.content,
            })

    if mensagens_saida:
        return (
            mensagens_saida[-1].content,
            input_tokens,
            output_tokens,
            evidencias,
        )

    return "", input_tokens, output_tokens, evidencias



@traceable(name="agente_faq", **_TRACE_NO)
def agente_faq(state: State) -> State:
    with span(state["trace_id"], "faq"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        mensagem = (
            f"ROUTE=faq\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}"
        )

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            faq_app,
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
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



@traceable(name="agente_receitas", **_TRACE_NO)
def agente_receitas(state: State) -> State:
    with span(state["trace_id"], "receitas"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

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

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            recipe_app,
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
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




@traceable(name="agente_estoque", **_TRACE_NO)
def agente_estoque(state: State) -> State:
    with span(state["trace_id"], "estoque"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        household_id = state.get(
            "household_account_id",
            0,
        )

        mensagem = (
            f"ROUTE=stock\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"PROFILE_ID={household_id}"
        )

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            stock_app,
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
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




@traceable(name="agente_eventos", **_TRACE_NO)
def agente_eventos(state: State) -> State:
    with span(state["trace_id"], "eventos"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

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

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            events_app,
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
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




def _formatar_evidencias(evidencias: list[dict]) -> str:
    """
    Monta o bloco de evidencias do juiz com o que as ferramentas devolveram,
    com teto de tamanho: o juiz roda a cada resposta e nao pode virar o
    gargalo de latencia da requisicao.
    """

    if not evidencias:
        return "nenhuma"

    linhas = []
    total = 0

    for evidencia in evidencias:
        ferramenta = evidencia.get("ferramenta", "ferramenta")
        conteudo = str(evidencia.get("conteudo", ""))[:LIMITE_EVIDENCIA]

        linha = f"- {ferramenta}: {conteudo}"
        total += len(linha)

        if total > LIMITE_EVIDENCIAS_TOTAL:
            linhas.append("- (demais retornos omitidos por tamanho)")
            break

        linhas.append(linha)

    return "\n".join(linhas)


def _formatar_conversa(historico: list[dict]) -> str:
    """
    Ultimos turnos, para o juiz poder ver repeticao e insistencia.

    Sem isto a regra de nao repetir pergunta ja respondida e inverificavel:
    o juiz recebia so a mensagem da vez.
    """

    if not historico:
        return "primeira mensagem da conversa"

    linhas = []

    for turno in historico[-TURNOS_PARA_O_JUIZ:]:
        quem = "usuário" if turno.get("role") == "user" else "Ceris"
        conteudo = str(turno.get("content", ""))[:LIMITE_EVIDENCIA]
        linhas.append(f"- {quem}: {conteudo}")

    return "\n".join(linhas)


def _ler_veredito(texto: str) -> tuple[str, str]:
    """
    Le as duas linhas do juiz.

    Falha para APROVADO de proposito: juiz que nao respondeu no formato, ou
    que devolveu sem dizer o motivo, nao e razao para travar a resposta do
    usuario.
    """

    veredito = "APROVADO"
    motivo = ""

    for linha in texto.splitlines():
        limpa = linha.strip()

        if limpa.upper().startswith("VEREDITO:"):
            if "DEVOLVER" in limpa.split(":", 1)[1].upper():
                veredito = "DEVOLVER"
        elif limpa.upper().startswith("MOTIVO:"):
            motivo = limpa.split(":", 1)[1].strip()

    if veredito == "DEVOLVER" and not motivo:
        return "APROVADO", ""

    return veredito, motivo


@traceable(name="juiz", **_TRACE_NO)
def juiz(state: State) -> State:
    with span(state["trace_id"], "juiz"):
        evidencias = _formatar_evidencias(state.get("evidencias", []))

        mensagem_usuario = (
            f"Rota: {state.get('rota', '')}\n"
            f"Conversa até agora:\n"
            f"{_formatar_conversa(state.get('historico', []))}\n"
            f"Pergunta: {state['mensagem']}\n"
            f"Evidências:\n"
            f"{evidencias}\n"
            f"Resposta do agente:\n"
            f"{state.get('resposta_agente', '')}"
        )

        resposta = fast_llm.invoke([
            SystemMessage(content=JUIZ_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        veredito, motivo = _ler_veredito(resposta.content)
        devolucoes = state.get("devolucoes", 0)

        if veredito == "DEVOLVER" and devolucoes < LIMITE_DEVOLUCOES:
            state["devolucoes"] = devolucoes + 1
            state["veredito_juiz"] = motivo
            state["limite_devolucoes"] = False
        else:
            state["veredito_juiz"] = ""
            state["limite_devolucoes"] = veredito == "DEVOLVER"

        input_tokens, output_tokens = extrair_tokens(resposta)
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.info(
            "juiz avaliou a resposta do agente",
            extra={
                "trace_id": state["trace_id"],
                "stage": "juiz",
                "rota": state.get("rota", ""),
                "veredito": veredito,
                "motivo": motivo,
                "devolucoes": state.get("devolucoes", 0),
                "limite_devolucoes": state.get("limite_devolucoes", False),
            },
        )

    return state



@traceable(name="orquestrador", **_TRACE_NO)
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

        if state.get("limite_devolucoes"):
            mensagem_usuario += "\nRevisão: não confirmada"

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



@traceable(name="guardrail_saida", **_TRACE_NO)
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

        bloqueado = resultado.get("bloqueado", False)
        devolucoes = state.get("devolucoes", 0)

        if bloqueado and devolucoes < LIMITE_DEVOLUCOES:
            state["devolucoes"] = devolucoes + 1
            state["saida_aprovada"] = False
        else:
            state["saida_aprovada"] = True

    return state



def decidir_pos_guardrail_entrada(state: State) -> str:
    if not state["entrada_aprovada"]:
        return "orquestrador"

    return "roteador"


def decidir_rota(state: State) -> str:
    return state["rota"]


def decidir_pos_juiz(state: State) -> str:
    if state.get("veredito_juiz"):
        rota = state.get("rota", "")

        if rota in ("receitas", "estoque", "eventos"):
            return rota

        return "orquestrador"

    return "orquestrador"


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
        with trace(
            name="ceris_chat_request",
            run_type="chain",
            metadata={
                "session_id": session_id,
                "household_account_id": household_account_id,
                "account_id": account_id,
                "trace_id": trace_id,
            },
        ):
            resultado = ceris_workflow.invoke({
                "mensagem": mensagem,
                "historico": historico,
                "rota": "fallback",
                "resposta_agente": "",
                "resposta_final": "",
                "entrada_aprovada": False,
                "saida_aprovada": False,
                "mapa_pii": {},
                "evidencias": [],
                "veredito_juiz": "",
                "devolucoes": 0,
                "limite_devolucoes": False,
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
    "juiz",
    juiz,
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
    "juiz",
)

graph.add_edge(
    "estoque",
    "juiz",
)

graph.add_edge(
    "eventos",
    "juiz",
)




graph.add_conditional_edges(
    "juiz",
    decidir_pos_juiz,
    {
        "receitas": "receitas",
        "estoque": "estoque",
        "eventos": "eventos",
        "orquestrador": "orquestrador",
    },
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