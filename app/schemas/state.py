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
    evidencias: list[dict]
    veredito_juiz: str
    devolucoes: int
    limite_devolucoes: bool
    household_account_id: int
    account_id: int
    trace_id: str
    input_tokens: int
    output_tokens: int
    decisoes_juiz: list[str]
    saida_bloqueada: bool
    lista_confirmada: bool
    juiz_aprovado: bool
    juiz_seguro: bool
    judge_usage: dict
