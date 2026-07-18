from typing import TypedDict


class State(TypedDict):
    mensagem: str
    historico: list[dict]
    rota: str
    resposta_agente: str
    resposta_final: str
    guardrail_entrada: bool
    guardrail_saida: bool
    mapa_pii: dict
