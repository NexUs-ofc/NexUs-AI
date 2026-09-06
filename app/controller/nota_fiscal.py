from fastapi import APIRouter
from ..model.dto.nota_fiscal_request import NotaFiscalRequest
from ..model.dto.nota_fiscal_response import NotaFiscalResponse
from ..schemas.flow_nota_fiscal import extrair_itens_nota_fiscal

router = APIRouter(prefix="/nota-fiscal")

@router.post("/", response_model=NotaFiscalResponse)
def ler_nota_fiscal(request: NotaFiscalRequest):
    resultado = extrair_itens_nota_fiscal(request.imagem_base64)
    return resultado
