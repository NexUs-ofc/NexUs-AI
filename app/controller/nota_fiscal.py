from fastapi import APIRouter
from ..model.dto.nota_fiscal_request import NotaFiscalRequest
from ..model.dto.nota_fiscal_response import NotaFiscalResponse
from ..model.dto.nota_fiscal_confirmacao_request import NotaFiscalConfirmacaoRequest
from ..model.dto.nota_fiscal_confirmacao_response import NotaFiscalConfirmacaoResponse
from ..schemas.flow_nota_fiscal import (
    extrair_itens_nota_fiscal,
    confirmar_e_salvar_itens_nota_fiscal,
)

router = APIRouter(prefix="/nota-fiscal")


@router.post("/", response_model=NotaFiscalResponse)
def ler_nota_fiscal(request: NotaFiscalRequest):
    return extrair_itens_nota_fiscal(request.imagem_base64)


@router.post("/confirmar", response_model=NotaFiscalConfirmacaoResponse)
def confirmar_itens_nota_fiscal(request: NotaFiscalConfirmacaoRequest):
    return confirmar_e_salvar_itens_nota_fiscal(request)