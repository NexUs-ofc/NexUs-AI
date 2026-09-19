from typing import TypedDict


class State(TypedDict):
    mensagem: str
    historico: list[dict]
    rota: str
    resposta_agente: str
    resposta_final: str
    entrada_aprovada: bool
    saida_aprovada: bool
    alucinacao_detectada: bool
    veredito_investigacao: str
    evidencias_investigacao: list
    replay_executado: bool
    mapa_pii: dict
    household_account_id: int
    account_id: int
    trace_id: str
    input_tokens: int
    output_tokens: int