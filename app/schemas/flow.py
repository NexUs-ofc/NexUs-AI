from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from .state import State
from app.core.llms import fast_llm
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO


def guardrail_entrada(state: State) -> State:
    state["guardrail_entrada"] = True
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
    state["resposta_final"] = state.get("resposta_agente", "")
    return state


def guardrail_saida(state: State) -> State:
    state["guardrail_saida"] = True
    return state


def decidir_pos_guardrail_entrada(state: State) -> str:
    if not state["guardrail_entrada"]:
        return "orquestrador"
    return "roteador"


def decidir_rota(state: State) -> str:
    return state["rota"]


def decidir_pos_guardrail_saida(state: State) -> str:
    if not state["guardrail_saida"]:
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
