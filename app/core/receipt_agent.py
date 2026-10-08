import base64
import json
import logging
import os
from collections.abc import Callable
from datetime import date, datetime, timedelta

from app.bases.shelf_life import DEFAULT_CATEGORIES, is_storable_food, shelf_life_days
from app.core.prompts.receipt import (
    RECEIPT_CLASSIFY_PROMPT,
    RECEIPT_ENRICH_PROMPT,
    RECEIPT_EXTRACT_PROMPT,
)
from app.schemas.receipt import ReceiptItem, ReceiptScanResponse
from app.tools.ocr_tools import decode_image, preprocess, read_receipt
from app.tools.receipt_parser import (
    deterministic_parse,
    ean_valid,
    items_sum,
    needs_deep_pass,
    norm,
)

logger = logging.getLogger("receipt")

RECENT_PURCHASE_DAYS = 30
UNKNOWN_NAME = "Item não identificado"


def _key() -> str | None:
    return os.getenv("GROQ_API_KEY")


def _text_model() -> str:
    return os.getenv("RECEIPT_TEXT_MODEL", "openai/gpt-oss-20b")


def _vision_model() -> str:
    return os.getenv("RECEIPT_VISION_MODEL", "qwen/qwen3.8-27b")


def _vision_enabled() -> bool:
    return os.getenv("RECEIPT_VISION_FALLBACK", "false").lower() == "true"

CatalogLookup = Callable[[list[str]], dict[str, dict]]


def _llm(model: str):
    from langchain_groq import ChatGroq

    extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
    return ChatGroq(
        model=model,
        temperature=0,
        api_key=_key(),
        max_retries=1,
        timeout=30,
        model_kwargs={"response_format": {"type": "json_object"}},
        **extra,
    )


def _ask_json(model: str, system: str, user_content) -> dict | None:
    if not _key():
        return None
    try:
        msg = _llm(model).invoke([("system", system), ("user", user_content)])
        text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
        return json.loads(text[text.find("{") : text.rfind("}") + 1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("receipt_llm_failed model=%s error=%s", model, exc)
        return None


def _name_items(items: list[dict], lines: list[str]) -> bool:
    payload = {
        "ocr_text": "\n".join(lines),
        "items": [{"id": i, "raw_text": it["raw_text"], "unit_price": it["unit_price"]} for i, it in enumerate(items)],
    }
    data = _ask_json(_text_model(), RECEIPT_ENRICH_PROMPT, json.dumps(payload, ensure_ascii=False))
    if not data or not isinstance(data.get("items"), list):
        return False
    by_id = {e.get("id"): e for e in data["items"] if isinstance(e, dict)}
    for i, it in enumerate(items):
        if not it["raw_text"]:
            it["name"] = UNKNOWN_NAME
            continue
        e = by_id.get(i)
        if not e:
            continue
        it["name"] = (e.get("name") or "").strip() or None
    return True


def _classify_items(items: list[dict], categories: list[str]) -> bool:
    payload = {
        "items": [
            {"id": i, "name": it.get("name") or it["raw_text"] or UNKNOWN_NAME}
            for i, it in enumerate(items)
        ]
    }
    system = RECEIPT_CLASSIFY_PROMPT.replace("{categories}", ", ".join(categories))
    data = _ask_json(_text_model(), system, json.dumps(payload, ensure_ascii=False))
    if not data or not isinstance(data.get("items"), list):
        return False
    by_id = {e.get("id"): e for e in data["items"] if isinstance(e, dict)}
    for i, it in enumerate(items):
        e = by_id.get(i)
        if not e:
            continue
        it["category"] = e.get("category") if e.get("category") in categories else None
        it["shelf_life_days"] = e.get("shelf_life_days")
    return True


def _enrich(items: list[dict], lines: list[str], categories: list[str]) -> bool:
    nomeou = _name_items(items, lines)
    classificou = _classify_items(items, categories)
    return nomeou or classificou


def _extract(lines: list[str] | None, image_bytes: bytes | None, categories: list[str]) -> dict | None:
    system = RECEIPT_EXTRACT_PROMPT.replace("{categories}", ", ".join(categories))
    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "text", "text": "Extraia os produtos desta nota fiscal."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
        return _ask_json(_vision_model(), system, content)
    return _ask_json(_text_model(), system, "\n".join(lines or []))


def _from_llm_extraction(data: dict) -> list[dict]:
    out = []
    for e in data.get("items") or []:
        if not isinstance(e, dict):
            continue
        ean = str(e.get("ean") or "").strip() or None
        out.append(
            {
                "raw_text": e.get("raw_text") or "",
                "name": e.get("name"),
                "ean": ean if ean_valid(ean) else None,
                "raw_ean": ean,
                "ean_candidates": [],
                "quantity": _num(e.get("quantity")) or 1,
                "unit": e.get("unit") or "un",
                "unit_price": _num(e.get("unit_price")),
                "category": e.get("category"),
                "shelf_life_days": e.get("shelf_life_days"),
            }
        )
    return out


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _apply_catalog(items: list[dict], lookup: CatalogLookup | None) -> None:
    if lookup is None:
        return
    codes = {c for it in items for c in ([it["ean"]] if it.get("ean") else it.get("ean_candidates", []))}
    if not codes:
        return
    try:
        found = lookup(sorted(codes))
    except Exception as exc:  # noqa: BLE001
        logger.warning("receipt_catalog_lookup_failed error=%s", exc)
        return
    for it in items:
        if not it.get("ean"):
            hits = [c for c in it.get("ean_candidates", []) if c in found]
            if len(hits) == 1:
                it["ean"] = hits[0]
                it["ean_candidates"] = []
        food = found.get(it.get("ean") or "")
        if food:
            it["food_id"] = food.get("food_id")
            it["name"] = it.get("name") or food.get("name")
            it["category"] = it.get("category") or food.get("category")


def _build_response(
    header: dict, items: list[dict], source: str, conf: float, warnings: list[str], categories: list[str]
) -> ReceiptScanResponse:
    today = datetime.now().astimezone().date()
    purchase = header.get("purchase_date")
    if isinstance(purchase, str):
        try:
            purchase = date.fromisoformat(purchase)
        except ValueError:
            purchase = None
    base = purchase if purchase and (today - purchase).days <= RECENT_PURCHASE_DAYS else today
    total = header.get("total")
    out_items = []
    for it in items:
        category = it.get("category") if it.get("category") in categories else None
        name = it.get("name") or it.get("raw_text") or UNKNOWN_NAME
        review = (
            not it.get("raw_text")
            or not it.get("ean")
            or it.get("unit_price") is None
            or name == UNKNOWN_NAME
        )
        out_items.append(
            ReceiptItem(
                name=name,
                raw_text=it.get("raw_text") or "",
                ean=it.get("ean"),
                ean_candidates=it.get("ean_candidates") or [],
                food_id=it.get("food_id"),
                quantity=it.get("quantity") or 1,
                unit=it.get("unit") or "un",
                unit_price=it.get("unit_price"),
                category=category,
                expiration_date=base + timedelta(days=shelf_life_days(category, it.get("shelf_life_days"))),
                needs_review=review,
            )
        )
    s = items_sum(items)
    if total is not None and abs(s - total) > 0.1:
        warnings.append(f"A soma dos itens lidos (R$ {s:.2f}) não bate com o total da nota (R$ {total:.2f}). Confira se faltou algum item.")
    food = [i for i in out_items if is_storable_food(i.category)]
    discarded = [i.name for i in out_items if i not in food]
    if discarded:
        warnings.append(
            "Itens que não vão para o estoque de alimentos foram deixados de fora: "
            + ", ".join(discarded)
            + "."
        )
    if any(i.needs_review for i in food):
        warnings.append("Alguns itens precisam de revisão antes de salvar.")
    return ReceiptScanResponse(
        store=header.get("store"),
        cnpj=header.get("cnpj"),
        purchase_date=purchase,
        total=total,
        items_total=s,
        items=food,
        source=source,
        ocr_confidence=conf,
        discarded=discarded,
        warnings=warnings,
    )


def _merge_same(items: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    out = []
    for it in items:
        key = it.get("ean") or norm(it.get("name") or it.get("raw_text") or "")
        if key and key in seen and seen[key].get("unit_price") == it.get("unit_price"):
            seen[key]["quantity"] = (seen[key].get("quantity") or 1) + (it.get("quantity") or 1)
            continue
        if key:
            seen[key] = it
        out.append(it)
    return out


def scan_receipt(
    image_bytes: bytes,
    categories: list[str] | None = None,
    catalog_lookup: CatalogLookup | None = None,
) -> ReceiptScanResponse:
    categories = categories or DEFAULT_CATEGORIES
    gray = preprocess(decode_image(image_bytes))
    ocr = read_receipt(gray)
    parsed = deterministic_parse(ocr["lines"])
    if needs_deep_pass(parsed):
        deep = read_receipt(gray, deep=True)
        deep_parsed = deterministic_parse(deep["lines"])
        if _score(deep_parsed) >= _score(parsed):
            ocr, parsed = deep, deep_parsed

    warnings: list[str] = []
    if not _looks_like_receipt(ocr["lines"], parsed):
        raise ValueError("not_a_receipt")

    items, source = parsed["items"], "ocr"
    header = {k: parsed.get(k) for k in ("store", "cnpj", "purchase_date", "total")}

    if not items:
        data = _extract(ocr["lines"], None, categories)
        if data:
            items, source = _merge_same(_from_llm_extraction(data)), "ocr+llm"
            header = {**header, **{k: v for k, v in data.items() if k in ("store", "purchase_date", "total") and v}}
    elif _enrich(items, ocr["lines"], categories):
        source = "ocr+llm"
    elif _key():
        warnings.append("Não foi possível enriquecer os nomes/categorias com IA; exibindo texto da nota.")

    if _vision_enabled() and _still_bad(items, header.get("total")):
        data = _extract(None, image_bytes, categories)
        vision_items = _merge_same(_from_llm_extraction(data)) if data else []
        if vision_items and _sum_ok(vision_items, header.get("total") or data.get("total")):
            items, source = vision_items, "vision"
            header = {**header, **{k: v for k, v in data.items() if k in ("store", "purchase_date", "total") and v}}

    _apply_catalog(items, catalog_lookup)
    return _build_response(header, items, source, ocr["mean_conf"], warnings, categories)


def _score(parsed: dict) -> float:
    items = parsed["items"]
    score = sum(1 for i in items if i["raw_text"]) + sum(1 for i in items if i["ean"]) + sum(
        0.5 for i in items if i.get("ean_candidates")
    )
    t = parsed.get("total")
    if t is not None and items and abs(items_sum(items) - t) <= 0.1:
        score += 5
    return score


def _sum_ok(items: list[dict], total) -> bool:
    t = _num(total)
    return t is not None and abs(items_sum(items) - t) <= 0.1


def _still_bad(items: list[dict], total) -> bool:
    if not items:
        return True
    if total is not None and not _sum_ok(items, total):
        return True
    return any(not i.get("raw_text") for i in items)


def _looks_like_receipt(lines: list[str], parsed: dict) -> bool:
    text = " ".join(lines).upper()
    hits = sum(k in text for k in ("CNPJ", "TOTAL", "CUPOM", "NFC", "FISCAL", "VALOR", "QTD", "R$", "RS"))
    return bool(parsed["items"]) or hits >= 2
