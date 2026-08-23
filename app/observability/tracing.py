import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.controller.config import logging
from app.repository.mongodb.traces import TracesRepository

logger = logging.getLogger(__name__)


def generate_trace_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def span(trace_id: str, name: str, extra: dict | None = None):
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()

    try:
        yield
    finally:
        finished_at = datetime.now(timezone.utc)
        duration_ms = (time.perf_counter() - started_perf) * 1000

        log_extra = {
            "trace_id": trace_id,
            "stage": "workflow",
            "span_name": name,
            "duration_ms": duration_ms,
        }

        if extra:
            log_extra.update(extra)

        logger.info(f"span {name}", extra=log_extra)

        TracesRepository.save_span(
            trace_id=trace_id,
            span_name=name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            extra=extra,
        )
