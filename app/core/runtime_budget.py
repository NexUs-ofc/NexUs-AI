"""Orçamento compartilhado entre nós e threads das chamadas de modelo."""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

_budget: ContextVar[dict | None] = ContextVar("model_budget", default=None)
logger = logging.getLogger(__name__)

# Um ciclo ReAct costuma consumir um passo do grafo para o modelo e outro para
# a ferramenta. O limite do agente precisa acompanhar as 12 chamadas de modelo
# do orçamento compartilhado; 16 passos cortavam pedidos válidos após ~7 tools.
MAX_MODEL_CALLS_PER_REQUEST = 12
AGENT_RECURSION_LIMIT = MAX_MODEL_CALLS_PER_REQUEST * 2 + 8
WORKFLOW_RECURSION_LIMIT = 32


class BudgetExceeded(RuntimeError):
    status_code = 503


@contextmanager
def request_budget(seconds=60.0, calls=MAX_MODEL_CALLS_PER_REQUEST, clock=time.monotonic):
    start = clock()
    context = {"deadline": start + seconds, "calls": 0, "limit": calls, "clock": clock, "lock": Lock()}
    mark = _budget.set(context)
    try:
        yield
    finally:
        logger.info("orçamento do chat encerrado", extra={"stage": "budget", "model_calls": context["calls"],
                    "max_model_calls": calls, "duration_ms": round((clock() - start) * 1000, 1)})
        _budget.reset(mark)


def remaining() -> float:
    context = _budget.get()
    return max(0, context["deadline"] - context["clock"]()) if context else float("inf")


def claim_model_call(model):
    context = _budget.get()
    if context is None:
        return
    timeout = getattr(model, "timeout", None) or getattr(model, "request_timeout", None)
    required = float(timeout) if isinstance(timeout, (float, int)) else 0
    with context["lock"]:
        if context["calls"] >= context["limit"] or remaining() <= required:
            raise BudgetExceeded("model_budget_exhausted")
        context["calls"] += 1
