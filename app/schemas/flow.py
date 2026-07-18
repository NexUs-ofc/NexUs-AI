from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from .state import State
from app.core.llms import fast_llm
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO
from app.core.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from app.guardrails.guardrails import anonimizar, checar_entrada, checar_saida


def guardrail_entrada(state: State) -> State:
    texto_anonimizado, mapa = anonimizar(state["mensagem"])
    state["mensagem"] = texto_anonimizado
    state["mapa_pii"] = mapa

    resultado = checar_entrada(texto_anonimizado)
    if resultado["bloqueado"]:
        state["entrada_aprovada"] = False
        state["resposta_agente"] = resultado["mensagem"]
    else:
        state["entrada_aprovada"] = True

    return state


def roteador(state: State) -> State:
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
    return state


def agente_faq(state: State) -> State:
    state["resposta_agente"] = ""
    return state


def agente_receitas(state: State) -> State:
    state["resposta_agente"] = ""
    return state


def agente_estoque(state: State) -> State:
    state["resposta_agente"] = ""
    return state


def agente_eventos(state: State) -> State:
    state["resposta_agente"] = ""
    return state


def orquestrador(state: State) -> State:
    resposta_agente = state.get("resposta_agente", "")
    rota = state.get("rota", "fallback")

    mensagem_usuario = (
        f"Rota: {rota}\n"
        f"Resposta do agente: \"{resposta_agente}\""
    )

    resposta = fast_llm.invoke([
        SystemMessage(content=ORQUESTRADOR_PROMPT_COMPLETO),
        HumanMessage(content=mensagem_usuario),
    ])

    state["resposta_final"] = resposta.content.strip()
    return state


def guardrail_saida(state: State) -> State:
    mapa = state.get("mapa_pii", {})
    resultado = checar_saida(state["resposta_final"], mapa)
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


graph = StateGraph(State)

graph.add_node("guardrail_entrada", guardrail_entrada)
graph.add_node("roteador", roteador)
graph.add_node("faq", agente_faq)
graph.add_node("receitas", agente_receitas)
graph.add_node("estoque", agente_estoque)
graph.add_node("eventos", agente_eventos)
graph.add_node("orquestrador", orquestrador)
graph.add_node("guardrail_saida", guardrail_saida)

graph.set_entry_point("guardrail_entrada")

graph.add_conditional_edges("guardrail_entrada", decidir_pos_guardrail_entrada, {
    "roteador": "roteador",
    "orquestrador": "orquestrador",
})

graph.add_conditional_edges("roteador", decidir_rota, {
    "faq": "faq",
    "receitas": "receitas",
    "estoque": "estoque",
    "eventos": "eventos",
    "fallback": "orquestrador",
})

graph.add_edge("faq", "orquestrador")
graph.add_edge("receitas", "orquestrador")
graph.add_edge("estoque", "orquestrador")
graph.add_edge("eventos", "orquestrador")

graph.add_edge("orquestrador", "guardrail_saida")

graph.add_conditional_edges("guardrail_saida", decidir_pos_guardrail_saida, {
    "orquestrador": "orquestrador",
    END: END,
})

app = graph.compile()
