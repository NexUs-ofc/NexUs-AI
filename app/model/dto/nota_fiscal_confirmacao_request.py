from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class ItemConfirmacaoRequest(BaseModel):
    nome: str
    marca: Optional[str] = None
    categoria: str
    quantidade: int = 1
    data_validade: Optional[date] = None
    peso: Optional[Decimal] = None
    unidade_medida: Optional[str] = "unit"


class NotaFiscalConfirmacaoRequest(BaseModel):
    household_account_id: int
    itens: list[ItemConfirmacaoRequest]