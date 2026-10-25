"""
De quem e a requisicao em andamento, para as tools.

O id da casa e da conta saia da mensagem montada para o agente
("PROFILE_ID=..."), e era o modelo quem o repassava para a tool. Ele copiava o
dos exemplos dos skills (PROFILE_ID=1, PROFILE_ID=7) e lia ou gravava no
estoque de outra casa. Agora o id vem do token, fica aqui durante a
requisicao, e as tools leem daqui: o modelo nao escolhe id nenhum.

ContextVar e nao variavel global: requisicoes simultaneas nao se misturam, e
o executor de tools do LangChain copia o contexto para as threads dele.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock

_perfil: ContextVar[int | None] = ContextVar("perfil", default=None)
_conta: ContextVar[int | None] = ContextVar("conta", default=None)
_gravacoes: ContextVar[tuple | None] = ContextVar("gravacoes", default=None)


class SemIdentidade(RuntimeError):
    """Tool chamada fora de uma requisicao: nao ha de quem ler ou gravar."""


@contextmanager
def da_requisicao(perfil: int, conta: int) -> Iterator[None]:
    marca_perfil = _perfil.set(perfil)
    marca_conta = _conta.set(conta)
    marca_gravacoes = _gravacoes.set(({}, RLock()))

    try:
        yield
    finally:
        _perfil.reset(marca_perfil)
        _conta.reset(marca_conta)
        _gravacoes.reset(marca_gravacoes)


def perfil() -> int:
    """Casa dona do estoque, das listas e dos eventos. Igual ao da Core."""

    valor = _perfil.get()

    if valor is None:
        raise SemIdentidade("Nenhuma casa definida para esta requisicao.")

    return valor


def conta() -> int:
    """Conta de quem conversa: memoria, preferencias e receitas salvas."""

    valor = _conta.get()

    if valor is None:
        raise SemIdentidade("Nenhuma conta definida para esta requisicao.")

    return valor



def executar_gravacao(operacao: str, dados: dict, acao):
    """Uma escrita idêntica por requisição, inclusive nas revisões do juiz.

    O contexto e a trava são compartilhados com as threads das ferramentas.
    Não guarda erros: uma falha pode ser tentada novamente.
    """
    context = _gravacoes.get()
    if context is None:
        raise SemIdentidade("Nenhuma requisição definida para gravar.")
    results, lock = context
    stable = {k: v for k, v in dados.items() if k not in {"created_at", "_id"}}
    key = (operacao, json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str))
    with lock:
        if key not in results:
            result = acao()
            if result is not None:
                results[key] = result
            return result
        return results[key]
