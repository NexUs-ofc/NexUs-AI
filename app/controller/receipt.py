import asyncio
import logging
import os
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.receipt_agent import scan_receipt
from app.observability.background import em_segundo_plano
from app.schemas.receipt import ReceiptScanResponse, ReceiptScanStatus
from app.tools.ocr_tools import liberar_memoria

from ..auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receipt", tags=["receipt"])

MAX_UPLOAD_MB = float(os.getenv("RECEIPT_MAX_UPLOAD_MB", "8"))
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/octet-stream"}

# Trava de thread, e nao de asyncio: as duas rotas (sincrona e por pedido)
# dividem a mesma, e uma leitura por vez e o que cabe na RAM do servidor.
_trava_leitura = threading.Semaphore(int(os.getenv("RECEIPT_MAX_CONCURRENCY", "1")))

# Pedido esquecido (app fechado no meio) nao fica na memoria para sempre.
VALIDADE_PEDIDO_S = int(os.getenv("RECEIPT_JOB_TTL_S", "900"))

_pedidos: dict[str, dict] = {}
_trava_pedidos = threading.Lock()

ERROS_CONHECIDOS = {
    "invalid_image": (400, "Não foi possível abrir a imagem."),
    "not_a_receipt": (422, "A imagem não parece ser uma nota fiscal."),
}


def get_categories() -> list[str] | None:
    return None


def get_catalog_lookup():
    return None


async def _ler_upload(image: UploadFile) -> bytes:
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Envie uma imagem JPEG, PNG ou WEBP.")
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem maior que {MAX_UPLOAD_MB:.0f} MB.")
    return data


def _registrar_leitura(inicio: datetime, fim: datetime, tipo_erro: str | None) -> None:
    """
    Grava a leitura na mesma coleção das métricas do chat, com a rota
    nota_fiscal, para o painel do admin contar leituras, tempo e sucesso.

    Fora do caminho da resposta, como o resto da telemetria. Sob pytest não
    grava: a suíte não toca rede, e a leitura é dublada nos testes.
    """

    if "pytest" in sys.modules:
        return

    from app.observability.tracing import generate_trace_id
    from app.repository.mongodb.metrics import MetricsRepository

    em_segundo_plano(
        MetricsRepository.save_request_metric,
        trace_id=generate_trace_id(),
        route="nota_fiscal",
        started_at=inicio,
        finished_at=fim,
        duration_ms=(fim - inicio).total_seconds() * 1000,
        tool_calls=0,
        error=tipo_erro is not None,
        error_type=tipo_erro,
    )


def _ler_com_trava(data: bytes) -> ReceiptScanResponse:
    with _trava_leitura:
        inicio = datetime.now(UTC)
        tipo_erro = None
        try:
            return scan_receipt(data, get_categories(), get_catalog_lookup())
        except ValueError as exc:
            tipo_erro = str(exc) if str(exc) in ERROS_CONHECIDOS else type(exc).__name__
            raise
        except Exception as exc:
            tipo_erro = type(exc).__name__
            raise
        finally:
            liberar_memoria()
            _registrar_leitura(inicio, datetime.now(UTC), tipo_erro)


@router.post("/scan", response_model=ReceiptScanResponse)
async def scan(
    user: Annotated[dict, Depends(get_current_user)],
    image: UploadFile = File(...),  # noqa: B008
) -> ReceiptScanResponse:
    """
    Leitura numa chamada so. Fica para compatibilidade: uma nota longa passa
    do tempo limite do app e do proxy, e o app usa a rota por pedido.
    """

    data = await _ler_upload(image)
    try:
        return await asyncio.to_thread(_ler_com_trava, data)
    except ValueError as exc:
        if str(exc) in ERROS_CONHECIDOS:
            codigo, detalhe = ERROS_CONHECIDOS[str(exc)]
            raise HTTPException(status_code=codigo, detail=detalhe) from exc
        raise


def _limpar_vencidos() -> None:
    limite = time.monotonic() - VALIDADE_PEDIDO_S
    with _trava_pedidos:
        for pedido_id in [p for p, v in _pedidos.items() if v["criado"] < limite]:
            del _pedidos[pedido_id]


def _atualizar(pedido_id: str, **campos) -> None:
    with _trava_pedidos:
        if pedido_id in _pedidos:
            _pedidos[pedido_id].update(campos)


def _processar(pedido_id: str, data: bytes) -> None:
    try:
        resultado = _ler_com_trava(data)
        _atualizar(pedido_id, status="pronto", resultado=resultado)
    except ValueError as exc:
        codigo, detalhe = ERROS_CONHECIDOS.get(str(exc), (500, "Não foi possível ler a nota."))
        _atualizar(pedido_id, status="erro", codigo=codigo, detalhe=detalhe)
    except Exception:
        logger.exception("leitura de nota falhou no pedido %s", pedido_id)
        _atualizar(pedido_id, status="erro", codigo=500, detalhe="Não foi possível ler a nota.")


@router.post("/scan/async", response_model=ReceiptScanStatus, status_code=202)
async def scan_async(
    user: Annotated[dict, Depends(get_current_user)],
    image: UploadFile = File(...),  # noqa: B008
) -> ReceiptScanStatus:
    """
    Recebe a foto e devolve um pedido na hora; a leitura segue em segundo
    plano. Nenhuma chamada fica aberta enquanto o OCR roda, entao o tempo
    limite do app e do proxy deixa de cortar nota longa.
    """

    data = await _ler_upload(image)
    _limpar_vencidos()

    pedido_id = uuid.uuid4().hex
    with _trava_pedidos:
        _pedidos[pedido_id] = {"dono": user["user_id"], "status": "processando", "criado": time.monotonic()}

    threading.Thread(target=_processar, args=(pedido_id, data), daemon=True, name=f"nota-{pedido_id[:8]}").start()

    return ReceiptScanStatus(pedido_id=pedido_id, status="processando")


@router.get("/scan/{pedido_id}", response_model=ReceiptScanStatus)
async def scan_status(
    pedido_id: str,
    user: Annotated[dict, Depends(get_current_user)],
) -> ReceiptScanStatus:
    with _trava_pedidos:
        pedido = dict(_pedidos.get(pedido_id) or {})

    # Pedido de outra pessoa responde igual a inexistente: nao confirma que existe.
    if not pedido or pedido["dono"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Leitura não encontrada. Envie a nota de novo.")

    return ReceiptScanStatus(
        pedido_id=pedido_id,
        status=pedido["status"],
        resultado=pedido.get("resultado"),
        codigo=pedido.get("codigo"),
        detalhe=pedido.get("detalhe"),
    )
