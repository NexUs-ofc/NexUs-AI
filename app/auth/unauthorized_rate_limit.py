"""Limita tentativas consecutivas que falham na autenticação por endereço IP."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field


@dataclass
class _Tentativas:
    falhas: deque[float] = field(default_factory=deque)
    bloqueado_ate: float = 0.0


class UnauthorizedRateLimiter:
    """Limitador em memória: 10 respostas 401 em 15 min bloqueiam por 15 min."""

    def __init__(
        self,
        limite: int = 10,
        janela_s: int = 15 * 60,
        bloqueio_s: int = 15 * 60,
        relogio=time.monotonic,
        max_ips: int = 10_000,
    ) -> None:
        self.limite = limite
        self.janela_s = janela_s
        self.bloqueio_s = bloqueio_s
        self._relogio = relogio
        self._max_ips = max_ips
        self._estados: OrderedDict[str, _Tentativas] = OrderedDict()
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int:
        agora = self._relogio()
        with self._lock:
            estado = self._estados.get(ip)
            if estado is None:
                return 0
            if estado.bloqueado_ate > agora:
                self._estados.move_to_end(ip)
                return max(1, int(estado.bloqueado_ate - agora + 0.999))
            if estado.bloqueado_ate:
                self._estados.pop(ip, None)
                return 0
            self._remover_expiradas(estado, agora)
            if not estado.falhas:
                self._estados.pop(ip, None)
            return 0

    def observar(self, ip: str, status_code: int) -> None:
        agora = self._relogio()
        with self._lock:
            if status_code != 401:
                self._estados.pop(ip, None)
                return

            estado = self._estados.setdefault(ip, _Tentativas())
            self._estados.move_to_end(ip)
            self._remover_expiradas(estado, agora)
            estado.falhas.append(agora)
            if len(estado.falhas) >= self.limite:
                estado.bloqueado_ate = agora + self.bloqueio_s

            while len(self._estados) > self._max_ips:
                self._estados.popitem(last=False)

    def _remover_expiradas(self, estado: _Tentativas, agora: float) -> None:
        while estado.falhas and agora - estado.falhas[0] > self.janela_s:
            estado.falhas.popleft()


def ip_cliente(headers, client_host: str | None) -> str:
    """Usa o IP validado pelo edge Cloudflare/Render; ignora X-Forwarded-For."""
    candidato = headers.get("cf-connecting-ip") or client_host or "unknown"
    try:
        return str(ipaddress.ip_address(candidato.strip()))
    except (ValueError, AttributeError):
        return "unknown"
