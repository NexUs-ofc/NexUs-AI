from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ..nota_fiscal.categoria import CategoriaProduto

UnidadeMedida = Literal["kg", "g", "l", "ml", "unit"]


class ItemNotaFiscal(BaseModel):
    """Item lido da nota. É o contrato de saída do agente E da API."""

    marca: str | None = Field(None, description="Marca do produto, ou null se não identificável.")
    nome: str = Field(..., min_length=1, description="Descrição do produto sem a marca.")
    categoria: CategoriaProduto = Field(CategoriaProduto.OUTROS, description="Categoria do ENUM.")
    quantidade: int = Field(1, ge=1, description="Unidades/embalagens compradas.")
    peso: float | None = Field(None, gt=0, description="Conteúdo da embalagem ou peso pesado.")
    unidade_medida: UnidadeMedida = Field("unit", description="Unidade do campo peso.")
    preco_unitario: float | None = Field(None, ge=0)
    preco_total: float | None = Field(None, ge=0)
    data_validade: date | None = None


class NotaFiscalExtraida(BaseModel):
    """Schema de saída estruturada do agente leitor de notas fiscais."""

    itens: list[ItemNotaFiscal] = Field(default_factory=list)
    legivel: bool = Field(True, description="False quando a imagem não é uma nota fiscal legível.")


class NotaFiscalResponse(BaseModel):
    itens: list[ItemNotaFiscal]
    legivel: bool = True
    trace_id: str | None = None
