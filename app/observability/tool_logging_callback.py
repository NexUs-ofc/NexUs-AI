import time
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler

from app.controller.config import logging
from app.repository.mongodb.tool_metrics import ToolMetricsRepository

logger = logging.getLogger(__name__)


class ToolLoggingCallback(BaseCallbackHandler):
    def __init__(self):
        super().__init__()
        self.trace_id: str | None = None
        self._starts: dict = {}

    def _resolve_trace_id(self, kwargs: dict) -> str | None:
        metadata = kwargs.get("metadata") or {}
        return metadata.get("trace_id") or self.trace_id

    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = kwargs.get("run_id")
        trace_id = self._resolve_trace_id(kwargs)
        tool_name = serialized.get("name", "unknown")

        self._starts[run_id] = (
            time.perf_counter(),
            datetime.now(timezone.utc),
            tool_name,
            trace_id,
        )

        logger.info(
            f"tool {tool_name} iniciada",
            extra={
                "trace_id": trace_id,
                "stage": "tool_usage",
                "tool_name": tool_name,
                "input_str": input_str,
            },
        )

    def on_tool_end(self, output, **kwargs):
        run_id = kwargs.get("run_id")
        started_perf, started_at, tool_name, trace_id = self._starts.pop(
            run_id,
            (time.perf_counter(), datetime.now(timezone.utc), "unknown", self._resolve_trace_id(kwargs)),
        )

        finished_at = datetime.now(timezone.utc)
        duration_ms = (time.perf_counter() - started_perf) * 1000

        logger.info(
            f"tool {tool_name} finalizada",
            extra={
                "trace_id": trace_id,
                "stage": "tool_usage",
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "output": str(output)[:500],
            },
        )

        ToolMetricsRepository.save_tool_call(
            trace_id=trace_id,
            tool_name=tool_name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            success=True,
        )

    def on_tool_error(self, error, **kwargs):
        run_id = kwargs.get("run_id")
        started_perf, started_at, tool_name, trace_id = self._starts.pop(
            run_id,
            (time.perf_counter(), datetime.now(timezone.utc), "unknown", self._resolve_trace_id(kwargs)),
        )

        finished_at = datetime.now(timezone.utc)
        duration_ms = (time.perf_counter() - started_perf) * 1000

        logger.error(
            f"tool {tool_name} falhou: {error}",
            extra={
                "trace_id": trace_id,
                "stage": "tool_usage",
                "tool_name": tool_name,
                "duration_ms": duration_ms,
            },
        )

        ToolMetricsRepository.save_tool_call(
            trace_id=trace_id,
            tool_name=tool_name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            success=False,
        )
