from datetime import date

from pydantic import BaseModel


class ItemConfirmadoResponse(BaseModel):
    pantry_item_id: int
    food_id: int
    nome: str
    marca: str | None = None
    categoria: str
    quantidade: int
    data_validade: date
    validade_estimada: bool = False


class NotaFiscalConfirmacaoResponse(BaseModel):
    sucesso: bool
    mensagem: str
    itens_salvos: list[ItemConfirmadoResponse]
