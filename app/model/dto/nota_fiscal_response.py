from pydantic import BaseModel
from typing import Optional


class ItemNotaFiscal(BaseModel):
    marca: str
    nome: str
    categoria: str
    quantidade: int
    preco_unitario: Optional[float] = None
    preco_total: Optional[float] = None


class NotaFiscalResponse(BaseModel):
    itens: list[ItemNotaFiscal]
