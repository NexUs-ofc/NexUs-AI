"""
Escritas de observabilidade fora do caminho crítico da requisição.

Span, métrica de tool e métrica de requisição são telemetria: ninguém espera
por elas para receber a resposta. Aguardadas em linha, custavam ~0,9s por
requisição com a conexão quente e ~3,8s na primeira, chegando a 66% do tempo
de uma saudação — mais do que todos os nós do grafo somados.

Thread e não asyncio porque os nós do grafo são síncronos; como é I/O de rede,
a thread solta a GIL enquanto espera o Atlas.

UM worker, não vários, e isso é proposital: a métrica da requisição conta as
chamadas de tool no Mongo, então precisa rodar depois das escritas das tools.
Fila FIFO de uma thread dá essa ordem de graça.

O histórico da conversa NÃO entra aqui. A requisição seguinte lê a conversa do
Mongo para montar o contexto, e adiar essa escrita faria o próximo turno
responder sem saber o que já foi dito.
"""

import atexit
from concurrent.futures import ThreadPoolExecutor, wait

from app.controller.config import logging

logger = logging.getLogger(__name__)

# Teto para o processo esperar a fila ao encerrar. Sem isto, um Atlas pausado
# ou uma rede caida penduram o shutdown pelo tempo que o driver levar para
# desistir — numa rodada de testes isso levou a suite de 15s para 59s.
SEGUNDOS_PARA_ESVAZIAR = 5

_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="observabilidade",
)

_pendentes: set = set()


def avisar(nivel: str, mensagem: str, **extras) -> None:
    """
    Loga de dentro da thread sem nunca estourar.

    Escrevendo em segundo plano, o log pode sair depois de o processo fechar o
    stream — o pytest fecha o stdout capturado e o logging levanta
    "I/O operation on closed file". Barulho que mataria a thread por nada.
    """

    try:
        getattr(logger, nivel)(mensagem, **extras)
    except Exception:  # noqa: BLE001, S110 - log que falha nao pode matar a thread
        pass


def _executar(funcao, args, kwargs) -> None:
    try:
        funcao(*args, **kwargs)
    except Exception:  # noqa: BLE001 - o avisar() abaixo registra com exc_info
        # Telemetria que falha não pode derrubar nada: a resposta da pessoa já
        # saiu daqui há muito tempo.
        avisar(
            "warning",
            f"escrita de observabilidade falhou em {funcao.__qualname__}",
            exc_info=True,
        )


def em_segundo_plano(funcao, *args, **kwargs) -> None:
    """Enfileira a escrita e devolve na hora."""

    try:
        futuro = _executor.submit(_executar, funcao, args, kwargs)
    except RuntimeError:
        # Pool já encerrado (desligando o processo): grava em linha para não
        # perder o último registro.
        _executar(funcao, args, kwargs)

        return

    _pendentes.add(futuro)
    futuro.add_done_callback(_pendentes.discard)


@atexit.register
def _esvaziar() -> None:
    """Dá um tempo para a fila terminar, mas não pendura o processo por ela."""

    if _pendentes:
        _, atrasados = wait(set(_pendentes), timeout=SEGUNDOS_PARA_ESVAZIAR)

        if atrasados:
            avisar(
                "warning",
                f"{len(atrasados)} escrita(s) de observabilidade descartada(s) "
                f"ao encerrar",
            )

    _executor.shutdown(wait=False, cancel_futures=True)
