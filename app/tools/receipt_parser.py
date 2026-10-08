import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

QTY_RE = re.compile(
    r"(\d+(?:[.,]\d{1,3})?)[\s\-.*:]*(UN|UND|KG|G|L|LT|ML|PC|PCT|CX|FD|DZ)[\s\-.*:]*[XxK×][\s\-.*:]*(\d+[.,]\s?\d{2})",
    re.I,
)
ITEM_RE = re.compile(r"^\s*(\d{1,3})?\s*(\d{7,15})\s*([A-Za-z].*)$")
EAN_ONLY_RE = re.compile(r"^\s*(\d{1,3})?\s*(\d{7,15})\s*$")
DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
CNPJ_RE = re.compile(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})")
MONEY_RE = re.compile(r"(\d+[.,]\d{2})")
HEADER_STOP = ("CUPOM", "DOCUMENTO AUXILIAR", "DANFE", "ITEM", "CODIGO", "DESCRICAO")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def to_float(s: str) -> float:
    return float(s.replace(" ", "").replace(",", "."))


def ean_valid(code: str | None) -> bool:
    if not code or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


CONFUSIONS = {"0": "86", "1": "7", "3": "8", "5": "6", "6": "85", "7": "1", "8": "063", "9": "8"}
TRAILING_RE = re.compile(r"\s+(F\s?[1T]|FT|F1T|I\d?|N\d?)\b.*$", re.I)


def ean_candidates(code: str | None) -> list[str]:
    if not code or len(code) != 13 or not code.isdigit() or ean_valid(code):
        return []
    out = []
    for i, c in enumerate(code):
        for r in CONFUSIONS.get(c, ""):
            cand = code[:i] + r + code[i + 1 :]
            if ean_valid(cand):
                out.append(cand)
    return out


def clean_desc(text: str) -> str:
    return TRAILING_RE.sub("", text).strip(" .,:-*")


def looks_like_desc(ln: str) -> bool:
    up = ln.upper()
    if QTY_RE.search(ln) or any(k in up for k in HEADER_STOP + ("TOTAL", "TROCO", "DINHEIRO", "CNPJ")):
        return False
    return len(re.findall(r"[A-Z]", up)) >= 4 and not re.search(r"\d{7,}", ln)


def split_index_ean(digits: str, expected_idx: int) -> tuple[int | None, str | None]:
    for k in range(0, 4):
        idx, ean = digits[:k], digits[k:]
        if ean_valid(ean) and (not idx or int(idx) <= expected_idx + 2):
            return (int(idx) if idx else None), ean
    exp = str(expected_idx)
    if digits.startswith(exp) and len(digits) - len(exp) >= 7:
        return expected_idx, None
    return None, None


def parse_header(lines: list[str]) -> dict:
    store, cnpj, purchase = None, None, None
    for ln in lines[:15]:
        up = ln.upper()
        if any(k in up for k in HEADER_STOP):
            break
        if store is None and re.search(r"[A-Z]{4,}", up) and not CNPJ_RE.search(ln):
            store = ln.strip()
    for ln in lines:
        if cnpj is None and (m := CNPJ_RE.search(ln)):
            cnpj = m.group(1)
        if purchase is None and (m := DATE_RE.search(ln)):
            d, mth, y = map(int, m.groups())
            try:
                purchase = date(y, mth, d)
            except ValueError:
                pass
    return {"store": store, "cnpj": cnpj, "purchase_date": purchase}


def parse_total(lines: list[str]) -> float | None:
    for i, ln in enumerate(lines):
        up = ln.upper()
        if re.search(r"(?<!SUB)TOTAL", up) and "ITENS" not in up:
            m = re.findall(r"(\d+[.,]\d{1,2})", ln)
            if m:
                return to_float(m[-1])
    return None


def parse_items(lines: list[str]) -> list[dict]:
    start = 0
    for i, ln in enumerate(lines):
        if any(k in ln.upper() for k in ("DESCRICAO", "CODIGO", "QTD")):
            start = i + 1
    items: list[dict] = []
    pending: dict | None = None
    orphan_desc: str | None = None
    seq = 1
    for ln in lines[start:]:
        if re.search(r"(?<!SUB)TOTAL", ln.upper()):
            break
        q = QTY_RE.search(ln)
        m = ITEM_RE.match(ln) if not q else None
        e = EAN_ONLY_RE.match(ln) if not q and not m else None
        if m or e:
            digits = (m or e).group(2)
            idx, ean = split_index_ean(((m or e).group(1) or "") + digits, seq)
            if ean is None and ean_valid(digits):
                ean = digits
            raw_ean = ean or (digits[-13:] if len(digits) >= 13 else digits)
            desc = clean_desc(m.group(3)) if m else ""
            if len(re.findall(r"[A-Za-z]", desc)) < 4 and orphan_desc:
                desc = orphan_desc
            orphan_desc = None
            pending = {
                "raw_text": desc,
                "ean": ean,
                "raw_ean": raw_ean,
                "ean_candidates": [] if ean else ean_candidates(raw_ean),
                "quantity": None,
                "unit": None,
                "unit_price": None,
            }
            items.append(pending)
            seq += 1
            continue
        if q:
            qty, unit, price = to_float(q.group(1)), q.group(2).lower(), to_float(q.group(3))
            unit = {"und": "un", "pc": "un", "pct": "un", "cx": "un", "fd": "un", "dz": "un", "lt": "l"}.get(unit, unit)
            if pending and pending["quantity"] is None:
                pending.update(quantity=qty, unit=unit, unit_price=price)
            else:
                items.append(
                    {"raw_text": orphan_desc or "", "ean": None, "raw_ean": None, "ean_candidates": [],
                     "quantity": qty, "unit": unit, "unit_price": price}
                )
                orphan_desc = None
            pending = None
            continue
        if looks_like_desc(ln):
            orphan_desc = clean_desc(ln)
    return items


def repair_and_merge(items: list[dict]) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    valid = [i for i in items if i["ean"] and i["raw_text"]]
    for it in items:
        if it["ean"] or not it["raw_text"]:
            continue
        best, score = None, 0.0
        for v in valid:
            r = SequenceMatcher(None, norm(it["raw_text"]), norm(v["raw_text"])).ratio()
            if r > score:
                best, score = v, r
        if best and score >= 0.8 and (it["unit_price"] is None or it["unit_price"] == best["unit_price"]):
            it["ean"] = best["ean"]
            it["ean_repaired"] = True
    merged: dict[str, dict] = {}
    out: list[dict] = []
    for it in items:
        key = it["ean"] or (norm(it["raw_text"]) if it["raw_text"] else None)
        if key and key in merged and merged[key]["unit_price"] == it["unit_price"]:
            merged[key]["quantity"] = (merged[key]["quantity"] or 1) + (it["quantity"] or 1)
            continue
        if key:
            merged[key] = it
        out.append(it)
    return out, warnings


def deterministic_parse(lines: list[str]) -> dict:
    header = parse_header(lines)
    total = parse_total(lines)
    raw_items = parse_items(lines)
    items, warnings = repair_and_merge(raw_items)
    return {**header, "total": total, "items": items, "raw_item_count": len(raw_items), "warnings": warnings}


def items_sum(items: list[dict]) -> float:
    return round(sum((i.get("quantity") or 0) * (i.get("unit_price") or 0) for i in items), 2)


def needs_deep_pass(parsed: dict) -> bool:
    items = parsed["items"]
    if not items:
        return True
    if any(not i["raw_text"] for i in items):
        return True
    if any(not i["ean"] for i in items if i.get("raw_ean")):
        return True
    t = parsed.get("total")
    return t is not None and abs(items_sum(items) - t) > 0.1
