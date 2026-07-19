from typing import TypedDict


class State(TypedDict):
    mensagem: str
    historico: list[dict]
    rota: str
    resposta_agente: str
    resposta_final: str
    entrada_aprovada: bool
    saida_aprovada: bool
    mapa_pii: dict
    household_account_id: int
    account_id: int
