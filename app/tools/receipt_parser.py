import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

QTY_RE = re.compile(
    r"(\d+(?:[.,]\d{1,3})?)[\s\-.*:]*(UNID|UND|UN|KG|G|ML|LT|L|PC|PCT|CX|FD|DZ|SACO|SAC|SC|POT|P[O0]|P[IT]|PT|TP)[\s\-.*:]*(?:[XxK×�][\s\-.*:]*)?(\d+[.,]\s?\d{2})",
    re.IGNORECASE,
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
TRAILING_RE = re.compile(r"\s+(F\s?[1T]|FT|F1T|I\d?|N\d?)\b.*$", re.IGNORECASE)


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


# O OCR troca a letra O por zero dentro de palavra ("ARR0Z", "T0RRAD0"), e o
# nome deixa de casar com o catalogo. So troca zero colado em letra: "500G"
# continua 500G.
ZERO_EM_PALAVRA_RE = re.compile(r"(?<=[A-Za-z])0|(?<![0-9])0(?=[A-Za-z])")


def clean_desc(text: str) -> str:
    return ZERO_EM_PALAVRA_RE.sub("O", TRAILING_RE.sub("", text)).strip(" .,:-*")


def looks_like_desc(ln: str) -> bool:
    up = ln.upper()
    if QTY_RE.search(ln) or any(k in up for k in HEADER_STOP + ("TOTAL", "TROCO", "DINHEIRO", "CNPJ")):
        return False
    return len(re.findall(r"[A-Z]", up)) >= 4 and not re.search(r"\d{7,}", ln)


def split_index_ean(digits: str, expected_idx: int) -> tuple[int | None, str | None]:
    for k in range(4):
        idx, ean = digits[:k], digits[k:]
        if ean_valid(ean) and (not idx or int(idx) <= expected_idx + 2):
            return (int(idx) if idx else None), ean
    exp = str(expected_idx)
    if digits.startswith(exp) and len(digits) - len(exp) >= 7:
        return expected_idx, None
    return None, None


def _is_item_header(line: str) -> bool:
    up = norm(line)
    colunas = ("COD", "DESCR", "QTD", "UNID", "PREC", "TOTAL", "ITEM")
    return sum(token in up for token in colunas) >= 3 and ("DESCR" in up or "COD" in up)


def parse_header(lines: list[str]) -> dict:
    store, cnpj, purchase = None, None, None
    for ln in lines[:15]:
        up = ln.upper()
        if _is_item_header(ln):
            continue
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
    # Cabecalho so vale antes do total: "QTD. TOTAL DE ITENS" vem depois dos
    # produtos em toda NFC-e e, contado como cabecalho, jogava o inicio para
    # depois deles — a nota voltava sem item nenhum.
    # O proprio cabecalho costuma ter "VL TOTAL", entao ele e testado antes.
    start = 0
    for i, ln in enumerate(lines):
        up = ln.upper()
        if _is_item_header(ln) or any(k in up for k in ("DESCRICAO", "CODIGO")) or ("QTD" in up and "TOTAL" not in up):
            start = i + 1
            continue
        if re.search(r"(?<!SUB)TOTAL", up):
            break

    items: list[dict] = []
    pending: dict | None = None
    orphan_desc: str | None = None
    seq = 1
    for ln in lines[start:]:
        if re.search(r"(?<!SUB)TOTAL", ln.upper()):
            break

        q = QTY_RE.search(ln)
        # Em muitos cupons codigo, descricao, quantidade e preco aparecem na
        # MESMA linha. Separar o prefixo antes de procurar EAN impede que a
        # presenca da quantidade esconda o produto e acabe criando item vazio.
        prefix = ln[: q.start()].strip() if q else ln.strip()
        m = ITEM_RE.match(prefix) if prefix else None
        e = EAN_ONLY_RE.match(prefix) if prefix and not m else None
        code_text = None
        desc_text = None
        if not m and not e and prefix:
            # O OCR por vezes cola a descricao ao EAN e troca um digito do
            # codigo por O/G/I/S. Recupera o limite do GTIN antes do texto.
            for tamanho in (14, 13, 12, 8):
                if len(prefix) <= tamanho:
                    continue
                candidato, resto = prefix[:tamanho], prefix[tamanho:]
                if re.fullmatch(r"[0-9OGQILSZB]+", candidato, re.IGNORECASE) and re.match(r"^[A-Za-z]", resto):
                    code_text, desc_text = candidato, resto
                    break

        if m or e or code_text:
            if code_text:
                digits = re.sub(r"[OGQILSZB]", lambda c: {"O": "0", "G": "6", "Q": "0", "I": "1", "L": "1", "S": "5", "Z": "2", "B": "8"}[c.group().upper()], code_text)
                _idx, ean = None, digits if ean_valid(digits) else None
                if ean is None:
                    candidatos = ean_candidates(digits)
                    ean = candidatos[0] if len(candidatos) == 1 else None
                raw_ean = ean or digits
                desc = clean_desc(desc_text or "")
            else:
                digits = ((m or e).group(1) or "") + (m or e).group(2)
                _idx, ean = split_index_ean(digits, seq)
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
        elif q and prefix and looks_like_desc(prefix):
            # Alguns caixas imprimem o sequencial do item junto do nome.
            prefix = re.sub(r"^\d{1,6}(?=[A-Za-z])", "", prefix)
            # Alguns cupons nao imprimem EAN: "PAO MINEIRO 1 UN X 6,49".
            # O parser antigo descartava a descricao porque testava a linha
            # completa (que ja continha quantidade) como texto de produto.
            orphan_desc = clean_desc(prefix)

        if q:
            qty, unit, price = to_float(q.group(1)), q.group(2).lower(), to_float(q.group(3))
            unit = {
                "und": "un", "unid": "un", "pc": "un", "pct": "un", "cx": "un",
                "fd": "un", "dz": "un", "sc": "un", "sac": "un", "saco": "un",
                "po": "un", "p0": "un", "pot": "un", "pt": "un", "pi": "un", "tp": "un", "lt": "l",
            }.get(unit, unit)
            if pending and pending["quantity"] is None:
                pending.update(quantity=qty, unit=unit, unit_price=price)
            else:
                items.append(
                    {"raw_text": orphan_desc or "", "ean": None, "raw_ean": None, "ean_candidates": [],
                     "quantity": qty, "unit": unit, "unit_price": price}
                )
            pending = None
            orphan_desc = None
            continue

        if m or e or code_text:
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
    # Codigo de barras ilegivel nao dispara a passada funda: ela roda o OCR mais
    # duas vezes (~45s medidos) e o app casa os itens pelo nome, nao pelo EAN.
    t = parsed.get("total")
    return t is not None and abs(items_sum(items) - t) > 0.1
