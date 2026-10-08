from datetime import date

from pydantic import BaseModel, Field


class ReceiptItem(BaseModel):
    name: str
    raw_text: str = ""
    ean: str | None = None
    ean_candidates: list[str] = Field(default_factory=list)
    food_id: int | None = None
    quantity: float = 1
    unit: str = "un"
    unit_price: float | None = None
    category: str | None = None
    expiration_date: date | None = None
    expiration_estimated: bool = True
    needs_review: bool = False


class ReceiptScanResponse(BaseModel):
    store: str | None = None
    cnpj: str | None = None
    purchase_date: date | None = None
    total: float | None = None
    items_total: float = 0
    items: list[ReceiptItem] = Field(default_factory=list)
    source: str = "ocr"
    ocr_confidence: float = 0
    discarded: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
