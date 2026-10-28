"""Uma troca de provedor apenas para falha transitória, sem retries aninhados."""

import time
from threading import Lock

import httpx
from langchain.agents.middleware import AgentMiddleware, ModelFallbackMiddleware
from langchain_core.runnables import Runnable

from .runtime_budget import BudgetExceeded, claim_model_call

# O mesmo provedor atende guardrail, roteador, seletor e agente. Se ele acabou
# de falhar de forma transitória, insistir nele em cada nó consome o orçamento
# inteiro antes que o fallback consiga concluir o pedido. O circuito é
# compartilhado entre as instâncias de modelo do processo e se recupera
# sozinho depois de um intervalo curto.
_CIRCUIT_SECONDS = 60.0
_circuit_lock = Lock()
_circuit_open_until: dict[str, float] = {}


def _model_key(model) -> str:
    return f"{type(model).__module__}.{type(model).__qualname__}"


def _circuit_open(model, clock=time.monotonic) -> bool:
    with _circuit_lock:
        return clock() < _circuit_open_until.get(_model_key(model), 0.0)


def _mark_failure(model, clock=time.monotonic) -> None:
    with _circuit_lock:
        _circuit_open_until[_model_key(model)] = clock() + _CIRCUIT_SECONDS


def _mark_success(model) -> None:
    with _circuit_lock:
        _circuit_open_until.pop(_model_key(model), None)


def transient(error: Exception) -> bool:
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None) or getattr(current, "code", None)
        if isinstance(status, int):
            return status in {408, 429, 500, 502, 503, 504, 529}
        if isinstance(current, (TimeoutError, ConnectionError, httpx.TransportError)):
            return True
        if type(current).__name__ in {"APITimeoutError", "APIConnectionError", "ServiceUnavailable",
                                     "DeadlineExceeded", "ResourceExhausted"}:
            return True
        current = getattr(current, "__cause__", None)
    return False


def _can_fallback(error: Exception) -> bool:
    # Esgotar o limite local não significa que o provedor falhou e não libera
    # uma chamada extra ao fallback. O workflow já transforma isso em resposta
    # controlada.
    return not isinstance(error, BudgetExceeded) and transient(error)


class TransientFallback(Runnable):
    def __init__(self, primary, fallbacks):
        self.runnable = primary
        if isinstance(fallbacks, (list, tuple)):
            self.fallbacks = list(fallbacks)
        else:
            self.fallbacks = [fallbacks] if fallbacks is not None else []
        # Compatibilidade com testes/código que inspecionam a primeira reserva.
        self.fallback = self.fallbacks[0] if self.fallbacks else None

    def _models(self):
        return [self.runnable, *self.fallbacks]

    def invoke(self, input, config=None, **kwargs):
        models = self._models()
        for index, model in enumerate(models):
            if index < len(models) - 1 and _circuit_open(model):
                continue
            try:
                claim_model_call(model)
                result = model.invoke(input, config=config, **kwargs)
                _mark_success(model)
                return result
            except Exception as error:
                if not _can_fallback(error) or index == len(models) - 1:
                    raise
                _mark_failure(model)
        raise RuntimeError("fallback_chain_empty")

    async def ainvoke(self, input, config=None, **kwargs):
        models = self._models()
        for index, model in enumerate(models):
            if index < len(models) - 1 and _circuit_open(model):
                continue
            try:
                claim_model_call(model)
                result = await model.ainvoke(input, config=config, **kwargs)
                _mark_success(model)
                return result
            except Exception as error:
                if not _can_fallback(error) or index == len(models) - 1:
                    raise
                _mark_failure(model)
        raise RuntimeError("fallback_chain_empty")


class TransientModelFallback(ModelFallbackMiddleware):
    def wrap_model_call(self, request, handler):
        models = [request.model, *self.models]
        for index, model in enumerate(models):
            if index < len(models) - 1 and _circuit_open(model):
                continue
            try:
                current = request if index == 0 else request.override(model=model)
                result = handler(current)
                _mark_success(model)
                return result
            except Exception as error:
                if not _can_fallback(error) or index == len(models) - 1:
                    raise
                _mark_failure(model)
        raise RuntimeError("fallback_chain_empty")

    async def awrap_model_call(self, request, handler):
        models = [request.model, *self.models]
        for index, model in enumerate(models):
            if index < len(models) - 1 and _circuit_open(model):
                continue
            try:
                current = request if index == 0 else request.override(model=model)
                result = await handler(current)
                _mark_success(model)
                return result
            except Exception as error:
                if not _can_fallback(error) or index == len(models) - 1:
                    raise
                _mark_failure(model)
        raise RuntimeError("fallback_chain_empty")


class CallBudgetMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        claim_model_call(request.model)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        claim_model_call(request.model)
        return await handler(request)
