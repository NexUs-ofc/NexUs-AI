import os
import threading

import cv2
import numpy as np

_engine = None
_lock = threading.Lock()

MAX_INPUT_SIDE = 1600
UPSCALE_TARGET = 2000
OCR_PARAMS = {"box_thresh": 0.3, "unclip_ratio": 1.8, "text_score": 0.3}
DET_MAX_SIDE = int(os.getenv("RECEIPT_DET_MAX_SIDE", "1280"))


def _get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                engine = RapidOCR()
                if DET_MAX_SIDE > 0:
                    resize = engine.text_detector.preprocess_op[0]
                    resize.limit_side_len = DET_MAX_SIDE
                    resize.limit_type = "max"
                _engine = engine
    return _engine


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid_image")
    return img


def preprocess(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) > MAX_INPUT_SIDE:
        s = MAX_INPUT_SIDE / max(h, w)
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = UPSCALE_TARGET / max(h, w)
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray


def _run(gray: np.ndarray) -> list[dict]:
    res, _ = _get_engine()(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), **OCR_PARAMS)
    out = []
    for box, text, conf in res or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        out.append(
            {
                "text": text.strip(),
                "conf": float(conf),
                "x0": min(xs),
                "x1": max(xs),
                "y0": min(ys),
                "y1": max(ys),
            }
        )
    return out


def _overlap(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    iy = max(0.0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
    inter = ix * iy
    if inter == 0:
        return 0.0
    area = min((a["x1"] - a["x0"]) * (a["y1"] - a["y0"]), (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area if area else 0.0


def _same(a: dict, b: dict) -> bool:
    ha, hb = a["y1"] - a["y0"], b["y1"] - b["y0"]
    return _overlap(a, b) >= 0.5 and min(ha, hb) / max(ha, hb) >= 0.6


def _merge(dets: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for d in sorted(dets, key=lambda d: -len(d["text"]) * d["conf"]):
        if all(not _same(d, k) for k in kept):
            kept.append(d)
    return kept


def _rows(dets: list[dict]) -> list[str]:
    dets = sorted(dets, key=lambda d: (d["y0"] + d["y1"]) / 2)
    rows: list[list[dict]] = []
    for d in dets:
        h = d["y1"] - d["y0"]
        best, best_score = None, 0.0
        for r in rows[-4:]:
            if any(min(d["x1"], x["x1"]) - max(d["x0"], x["x0"]) > 0 for x in r):
                continue
            score = max(
                (min(d["y1"], x["y1"]) - max(d["y0"], x["y0"])) / min(h, x["y1"] - x["y0"]) for x in r
            )
            if score > best_score:
                best, best_score = r, score
        if best is not None and best_score >= 0.5:
            best.append(d)
        else:
            rows.append([d])
    rows.sort(key=lambda r: min(x["y0"] for x in r))
    return [" ".join(x["text"] for x in sorted(r, key=lambda x: x["x0"])) for r in rows]


def read_receipt(gray: np.ndarray, deep: bool = False) -> dict:
    dets = _run(gray)
    if deep:
        dets += _run(cv2.GaussianBlur(gray, (0, 0), 2.5))
        dets += _run(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 12))
        dets = _merge(dets)
    conf = sum(d["conf"] for d in dets) / len(dets) if dets else 0.0
    return {"lines": _rows(dets), "mean_conf": round(conf, 3)}
