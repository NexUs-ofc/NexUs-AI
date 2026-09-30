from datetime import date
from typing import Optional
from pydantic import BaseModel


class ItemNotaFiscal(BaseModel):
    marca: Optional[str] = None
    nome: str
    categoria: str
    quantidade: int = 1
    preco_unitario: Optional[float] = None
    preco_total: Optional[float] = None
    peso: Optional[float] = None
    data_validade: Optional[date] = None


class NotaFiscalResponse(BaseModel):
    itens: list[ItemNotaFiscal]