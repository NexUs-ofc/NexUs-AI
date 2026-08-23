from datetime import datetime, timedelta, timezone

from app.repository.mongodb.metrics import MetricsRepository
from app.repository.mongodb.tool_metrics import ToolMetricsRepository


def _iso_z(momento: datetime) -> str:
    return momento.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _agregar_por_minuto(collection, janela_inicio: datetime, campos: dict) -> list[dict]:
    pipeline = [
        {"$match": {"started_at": {"$gte": janela_inicio}}},
        {
            "$group": {
                "_id": {"$dateTrunc": {"date": "$started_at", "unit": "minute"}},
                **campos,
            }
        },
        {"$sort": {"_id": 1}},
    ]

    return list(collection.aggregate(pipeline))


def _montar_series(rows: list[dict], valor_de: callable) -> list[dict]:
    return [
        {"minute": _iso_z(row["_id"]), "value": valor_de(row)}
        for row in rows
    ]


def _valor_do_minuto(serie: list[dict], minuto_alvo: str):
    for item in serie:
        if item["minute"] == minuto_alvo:
            return item["value"]

    return 0


def build_summary() -> dict:
    agora = datetime.now(timezone.utc)
    janela_inicio = agora - timedelta(minutes=60)
    ultimo_minuto_fechado = agora.replace(second=0, microsecond=0) - timedelta(minutes=1)
    minuto_alvo = _iso_z(ultimo_minuto_fechado)

    metrics_rows = _agregar_por_minuto(
        MetricsRepository.metrics_collection,
        janela_inicio,
        {
            "count": {"$sum": 1},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "error_count": {"$sum": {"$cond": ["$error", 1, 0]}},
        },
    )

    tool_rows = _agregar_por_minuto(
        ToolMetricsRepository.tool_metrics_collection,
        janela_inicio,
        {"count": {"$sum": 1}},
    )

    requests_series = _montar_series(metrics_rows, lambda row: row["count"])
    latency_series = _montar_series(
        metrics_rows,
        lambda row: round(row["avg_duration_ms"] or 0, 1),
    )
    error_rate_series = _montar_series(
        metrics_rows,
        lambda row: round((row["error_count"] / row["count"]) * 100, 2) if row["count"] else 0,
    )
    tool_calls_series = _montar_series(tool_rows, lambda row: row["count"])

    return {
        "current": {
            "requests_per_minute": _valor_do_minuto(requests_series, minuto_alvo),
            "avg_latency_ms": _valor_do_minuto(latency_series, minuto_alvo),
            "error_rate_pct": _valor_do_minuto(error_rate_series, minuto_alvo),
            "tool_calls_per_minute": _valor_do_minuto(tool_calls_series, minuto_alvo),
            "status": "online",
        },
        "series": {
            "requests_per_minute": requests_series,
            "avg_latency_ms": latency_series,
            "error_rate_pct": error_rate_series,
            "tool_calls_per_minute": tool_calls_series,
        },
    }


def build_cost_summary(
    requests_per_user_per_week: int = 20,
    value_per_resolution_usd: float = 0.0,
) -> dict:
    janela_inicio = datetime.now(timezone.utc) - timedelta(days=7)

    pipeline = [
        {"$match": {"started_at": {"$gte": janela_inicio}}},
        {
            "$group": {
                "_id": None,
                "total_requests": {"$sum": 1},
                "resolved_requests": {"$sum": {"$cond": ["$error", 0, 1]}},
                "total_cost_usd": {"$sum": "$cost_usd"},
                "total_input_tokens": {"$sum": "$input_tokens"},
                "total_output_tokens": {"$sum": "$output_tokens"},
            }
        },
    ]

    rows = list(MetricsRepository.metrics_collection.aggregate(pipeline))
    linha = rows[0] if rows else {}

    total_requests = linha.get("total_requests", 0)
    resolved_requests = linha.get("resolved_requests", 0)
    total_cost_usd = linha.get("total_cost_usd", 0.0) or 0.0

    avg_cost_per_request_usd = (total_cost_usd / total_requests) if total_requests else 0.0
    cost_per_resolution_usd = (total_cost_usd / resolved_requests) if resolved_requests else None

    roi_pct = None

    if total_cost_usd > 0 and value_per_resolution_usd > 0:
        retorno_total = value_per_resolution_usd * resolved_requests
        roi_pct = round(((retorno_total - total_cost_usd) / total_cost_usd) * 100, 2)

    return {
        "window_days": 7,
        "total_requests": total_requests,
        "resolved_requests": resolved_requests,
        "total_cost_usd": round(total_cost_usd, 6),
        "total_input_tokens": linha.get("total_input_tokens", 0),
        "total_output_tokens": linha.get("total_output_tokens", 0),
        "avg_cost_per_request_usd": round(avg_cost_per_request_usd, 6),
        "cost_per_resolution_usd": (
            round(cost_per_resolution_usd, 6) if cost_per_resolution_usd is not None else None
        ),
        "estimated_weekly_cost_100_users_usd": round(
            avg_cost_per_request_usd * requests_per_user_per_week * 100, 2
        ),
        "estimated_weekly_cost_1000_users_usd": round(
            avg_cost_per_request_usd * requests_per_user_per_week * 1000, 2
        ),
        "requests_per_user_per_week": requests_per_user_per_week,
        "value_per_resolution_usd": value_per_resolution_usd,
        "roi_pct": roi_pct,
    }
