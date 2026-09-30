from datetime import date
from typing import Optional
from pydantic import BaseModel


class ItemConfirmadoResponse(BaseModel):
    pantry_item_id: int
    food_id: int
    nome: str
    marca: Optional[str] = None
    categoria: str
    quantidade: int
    data_validade: Optional[date] = None


class NotaFiscalConfirmacaoResponse(BaseModel):
    sucesso: bool
    mensagem: str
    itens_salvos: list[ItemConfirmadoResponse]