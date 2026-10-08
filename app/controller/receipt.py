import asyncio
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.receipt_agent import scan_receipt
from app.schemas.receipt import ReceiptScanResponse

router = APIRouter(prefix="/receipt", tags=["receipt"])

MAX_UPLOAD_MB = float(os.getenv("RECEIPT_MAX_UPLOAD_MB", "8"))
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/octet-stream"}
_semaphore = asyncio.Semaphore(int(os.getenv("RECEIPT_MAX_CONCURRENCY", "1")))


def get_categories() -> list[str] | None:
    return None


def get_catalog_lookup():
    return None


@router.post("/scan", response_model=ReceiptScanResponse)
async def scan(image: UploadFile = File(...), profile_id: int | None = Form(None)) -> ReceiptScanResponse:  # noqa: B008
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Envie uma imagem JPEG, PNG ou WEBP.")
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem maior que {MAX_UPLOAD_MB:.0f} MB.")
    async with _semaphore:
        try:
            return await asyncio.to_thread(scan_receipt, data, get_categories(), get_catalog_lookup())
        except ValueError as exc:
            if str(exc) == "invalid_image":
                raise HTTPException(status_code=400, detail="Não foi possível abrir a imagem.")
            if str(exc) == "not_a_receipt":
                raise HTTPException(status_code=422, detail="A imagem não parece ser uma nota fiscal.")
            raise
