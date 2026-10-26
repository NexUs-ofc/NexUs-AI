"""Cliente TypeSafe com pool, retry transitório limitado e circuit breaker."""

import math
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock

import httpx

from .runtime_budget import remaining as request_remaining


class JevUnavailable(RuntimeError):
    """Erro de avaliação sem incluir payload, chave ou resposta do provedor."""


class JevClient:
    URL = "https://api.typesafe.ai/v1/systemone"
    RETRYABLE = frozenset({408, 429, 500, 502, 503, 504, 529})

    def __init__(self, api_key: str, model: str = "jev-latest", *, client=None,
                 budget: float = 5.0, attempts: int = 2, clock=time.monotonic,
                 sleep=time.sleep, jitter=random.uniform):
        self._key = api_key
        self.model = model
        self.budget = budget
        self.attempts = attempts
        self.clock, self.sleep, self.jitter = clock, sleep, jitter
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(3, connect=1.5, pool=0.5),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            trust_env=False, follow_redirects=False,
        )
        self._lock = Lock()
        self._failures = 0
        self._open_until = 0.0
        self._probe = False

    def _enter(self):
        with self._lock:
            if not self._key or self.clock() < self._open_until:
                raise JevUnavailable("jev_unavailable")
            if self._failures >= 3:
                if self._probe:
                    raise JevUnavailable("jev_circuit_open")
                self._probe = True

    def _finish(self, success: bool):
        with self._lock:
            self._probe = False
            self._failures = 0 if success else self._failures + 1
            if self._failures >= 3:
                self._open_until = self.clock() + 30

    @staticmethod
    def _retry_after(value: str | None) -> float:
        if not value:
            return 0
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return 0
        return max(0, seconds) if math.isfinite(seconds) else 0

    def evaluate(self, state: dict, questions: dict) -> dict:
        budget = min(self.budget, request_remaining())
        if budget <= 0:
            raise JevUnavailable("jev_budget_exhausted")
        self._enter()
        started = self.clock()
        success = False
        try:
            for attempt in range(self.attempts):
                remaining = budget - (self.clock() - started)
                if remaining <= 0:
                    raise JevUnavailable("jev_budget_exhausted")
                delay = 0.0
                try:
                    response = self.client.post(
                        self.URL, headers={"Authorization": f"Bearer {self._key}"},
                        json={"model": self.model, "state": state, "questions": questions},
                        timeout=httpx.Timeout(min(3, remaining), connect=min(1.5, remaining),
                                              pool=min(0.5, remaining)),
                    )
                    if response.status_code == 200:
                        try:
                            result = response.json()
                        except ValueError:
                            raise JevUnavailable("jev_invalid_json") from None
                        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
                            raise JevUnavailable("jev_invalid_response")
                        success = True
                        return result
                    if response.status_code not in self.RETRYABLE:
                        raise JevUnavailable(f"jev_http_{response.status_code}")
                    delay = self._retry_after(response.headers.get("Retry-After"))
                except httpx.TransportError:
                    pass
                if attempt + 1 >= self.attempts:
                    break
                delay = max(delay, self.jitter(0, min(0.5, 0.15 * 2 ** attempt)))
                if delay + 0.05 >= budget - (self.clock() - started):
                    break
                self.sleep(delay)
            raise JevUnavailable("jev_transient_failure")
        finally:
            self._finish(success)


_shared_client = None
_shared_lock = Lock()


def get_jev_client() -> JevClient:
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            from app.config import JEV_MODEL, TYPESAFE_API_KEY
            _shared_client = JevClient(TYPESAFE_API_KEY, JEV_MODEL)
    return _shared_client
