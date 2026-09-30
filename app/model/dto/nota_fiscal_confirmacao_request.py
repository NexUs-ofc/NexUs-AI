from pydantic import BaseModel, Field

from .nota_fiscal_response import ItemNotaFiscal


class NotaFiscalConfirmacaoRequest(BaseModel):
    """
    Itens revisados pelo usuário no app após a leitura da nota.

    O fluxo é em duas etapas (ler -> usuário confirma/edita -> salvar) para que
    nada gerado pelo modelo entre no estoque sem revisão humana.
    """

    household_account_id: int = Field(..., gt=0)
    itens: list[ItemNotaFiscal] = Field(..., min_length=1, max_length=200)
