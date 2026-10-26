"""Uma troca de provedor apenas para falha transitória, sem retries aninhados."""

import httpx
from langchain.agents.middleware import AgentMiddleware, ModelFallbackMiddleware
from langchain_core.runnables import Runnable

from .runtime_budget import claim_model_call


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


class TransientFallback(Runnable):
    def __init__(self, primary, fallback):
        self.runnable, self.fallback = primary, fallback

    def invoke(self, input, config=None, **kwargs):
        try:
            claim_model_call(self.runnable)
            return self.runnable.invoke(input, config=config, **kwargs)
        except Exception as error:
            if not transient(error) or self.fallback is None:
                raise
        claim_model_call(self.fallback)
        return self.fallback.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        try:
            claim_model_call(self.runnable)
            return await self.runnable.ainvoke(input, config=config, **kwargs)
        except Exception as error:
            if not transient(error) or self.fallback is None:
                raise
        claim_model_call(self.fallback)
        return await self.fallback.ainvoke(input, config=config, **kwargs)


class TransientModelFallback(ModelFallbackMiddleware):
    def wrap_model_call(self, request, handler):
        try:
            return handler(request)
        except Exception as error:
            if not transient(error):
                raise
        return handler(request.override(model=self.models[0]))

    async def awrap_model_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as error:
            if not transient(error):
                raise
        return await handler(request.override(model=self.models[0]))


class CallBudgetMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        claim_model_call(request.model)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        claim_model_call(request.model)
        return await handler(request)
