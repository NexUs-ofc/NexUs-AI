from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..auth.dependencies import get_current_user
from ..controller.config import logging
from ..model.dto.nota_fiscal_confirmacao_request import NotaFiscalConfirmacaoRequest
from ..model.dto.nota_fiscal_confirmacao_response import NotaFiscalConfirmacaoResponse
from ..model.dto.nota_fiscal_request import NotaFiscalRequest
from ..model.dto.nota_fiscal_response import NotaFiscalResponse
from ..schemas.flow_nota_fiscal import (
    ImagemInvalidaError,
    LeituraNotaFiscalError,
    confirmar_e_salvar_itens_nota_fiscal,
    extrair_itens_nota_fiscal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nota-fiscal")


@router.post("/", response_model=NotaFiscalResponse)
def ler_nota_fiscal(
    request: NotaFiscalRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Lê a imagem da nota e devolve os itens para revisão (não grava nada)."""

    try:
        return extrair_itens_nota_fiscal(request.imagem_base64)
    except ImagemInvalidaError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LeituraNotaFiscalError as erro:
        logger.warning(f"Falha na leitura estruturada da nota: {erro}")
        raise HTTPException(
            status_code=502,
            detail="Não foi possível ler a nota fiscal. Tente uma foto mais nítida.",
        ) from erro


@router.post("/confirmar", response_model=NotaFiscalConfirmacaoResponse)
def confirmar_itens_nota_fiscal(
    request: NotaFiscalConfirmacaoRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Grava no estoque os itens revisados/confirmados pelo usuário."""

    resultado = confirmar_e_salvar_itens_nota_fiscal(request)

    if not resultado.sucesso:
        raise HTTPException(status_code=500, detail=resultado.mensagem)

    return resultado
