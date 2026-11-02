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
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import RLock

_perfil: ContextVar[int | None] = ContextVar("perfil", default=None)
_conta: ContextVar[int | None] = ContextVar("conta", default=None)
_gravacoes: ContextVar[tuple | None] = ContextVar("gravacoes", default=None)
_assunto: ContextVar[dict | None] = ContextVar("assunto", default=None)
_leituras: ContextVar[tuple | None] = ContextVar("leituras", default=None)
_somente_leitura: ContextVar[bool] = ContextVar("somente_leitura", default=False)
_reparos: ContextVar[list | None] = ContextVar("reparos", default=None)
_autorizador_gravacao: ContextVar[object | None] = ContextVar("autorizador_gravacao", default=None)
_gravacao_negada: ContextVar[bool] = ContextVar("gravacao_negada", default=False)
_operacoes_pendentes: ContextVar[tuple | None] = ContextVar("operacoes_pendentes", default=None)
_gravacao_aprovada: ContextVar[list | None] = ContextVar("gravacao_aprovada", default=None)
_relatorio_operacoes: ContextVar[list | None] = ContextVar("relatorio_operacoes", default=None)
_INCERTA = object()
_NEGADA = object()
logger = logging.getLogger(__name__)


class SemIdentidade(RuntimeError):
    """Tool chamada fora de uma requisicao: nao ha de quem ler ou gravar."""


@contextmanager
def da_requisicao(perfil: int, conta: int, assunto: dict | None = None,
                  autorizador_gravacao=None) -> Iterator[None]:
    marca_perfil = _perfil.set(perfil)
    marca_conta = _conta.set(conta)
    marca_gravacoes = _gravacoes.set(({}, RLock()))
    marca_assunto = _assunto.set(deepcopy(assunto))
    marca_leituras = _leituras.set(({}, RLock()))
    marca_reparo = _somente_leitura.set(False)
    marca_limite_reparos = _reparos.set([0, RLock()])
    marca_autorizador = _autorizador_gravacao.set(autorizador_gravacao)
    marca_gravacao_negada = _gravacao_negada.set(False)
    marca_operacoes = _operacoes_pendentes.set(([], RLock()))
    marca_permissoes = _gravacao_aprovada.set(None)
    marca_relatorio = _relatorio_operacoes.set([])

    try:
        yield
    finally:
        _perfil.reset(marca_perfil)
        _conta.reset(marca_conta)
        _gravacoes.reset(marca_gravacoes)
        _assunto.reset(marca_assunto)
        _leituras.reset(marca_leituras)
        _somente_leitura.reset(marca_reparo)
        _reparos.reset(marca_limite_reparos)
        _autorizador_gravacao.reset(marca_autorizador)
        _gravacao_negada.reset(marca_gravacao_negada)
        _operacoes_pendentes.reset(marca_operacoes)
        _gravacao_aprovada.reset(marca_permissoes)
        _relatorio_operacoes.reset(marca_relatorio)


def adiar_operacao(nome: str, argumentos, justificativa: str) -> str:
    """Armazena os argumentos tipados da operação para validação do juiz."""
    context = _operacoes_pendentes.get()
    if context is None:
        raise SemIdentidade("Nenhuma requisição definida para adiar a operação.")
    if not isinstance(argumentos, dict) and not callable(getattr(argumentos, "model_dump", None)):
        raise TypeError("Os argumentos adiados precisam corresponder ao schema da ferramenta.")
    queue, lock = context
    with lock:
        operacao_id = f"op-{len(queue) + 1}"
        queue.append({"id": operacao_id, "operacao": nome,
                      "argumentos": deepcopy(argumentos), "justificativa": justificativa})
    return f"Operação {operacao_id} registrada para validação; ainda não foi executada."


def obter_operacoes_pendentes() -> list[dict]:
    context = _operacoes_pendentes.get()
    if context is None:
        return []
    queue, lock = context
    with lock:
        pending = deepcopy(queue)
        queue.clear()
    return pending


def registrar_resultado_operacao(operacao: str, status: str, detalhe: str = "") -> None:
    report = _relatorio_operacoes.get()
    if report is not None:
        report.append({"operacao": operacao, "status": status, "detalhe": detalhe})
    if status != "concluida":
        _gravacao_negada.set(True)


def relatorio_operacoes() -> list[dict]:
    return deepcopy(_relatorio_operacoes.get() or [])


@contextmanager
def permitir_gravacao_aprovada(operacao: str, dados: dict):
    """Autoriza uma única gravação feita pela tool aprovada no dispatcher."""
    mark = _gravacao_aprovada.set([1])
    try:
        yield
    finally:
        _gravacao_aprovada.reset(mark)


def reservar_reparo() -> bool:
    """Confirmação de escrita e juiz compartilham UMA correção por pedido."""
    context = _reparos.get()
    if context is None:
        return True
    with context[1]:
        if context[0] >= 1:
            return False
        context[0] += 1
        return True


def tem_gravacao() -> bool:
    context = _gravacoes.get()
    if context is None:
        return False
    results, lock = context
    with lock:
        return bool(results)


def escrita_incerta() -> bool:
    context = _gravacoes.get()
    if context is None:
        return False
    with context[1]:
        return any(value is _INCERTA for value in context[0].values())


def gravacao_negada() -> bool:
    return _gravacao_negada.get()


@contextmanager
def reparo_de_resposta():
    """Após uma escrita confirmada/incerta, revisão só lê ou reutiliza recibos."""
    mark = _somente_leitura.set(_somente_leitura.get() or tem_gravacao())
    try:
        yield
    finally:
        _somente_leitura.reset(mark)


def consultar_uma_vez(nome: str, acao):
    context = _leituras.get()
    if context is None:
        return acao()
    cache, lock = context
    with lock:
        if nome not in cache:
            result = acao()
            if not isinstance(result, str) or not result.startswith("FALHA"):
                cache[nome] = result
            return result
        return cache[nome]


def assunto() -> dict | None:
    """Origem do pedido vinda da sessão, não escolhida pelo modelo."""
    return deepcopy(_assunto.get())


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
    Falhas explícitas None/False podem ser tentadas novamente. Exceção após
    iniciar a escrita é incerta e bloqueia repetição automática.
    """
    context = _gravacoes.get()
    if context is None:
        raise SemIdentidade("Nenhuma requisição definida para gravar.")
    results, lock = context
    stable = {k: v for k, v in dados.items() if k not in {"created_at", "_id"}}
    key = (operacao, json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str))
    with lock:
        grant = _gravacao_aprovada.get()
        pre_aprovada = grant is not None and grant[0] > 0
        if pre_aprovada:
            grant[0] -= 1
        if key not in results:
            if _somente_leitura.get():
                return None
            autorizar = _autorizador_gravacao.get()
            if autorizar is not None and not pre_aprovada:
                try:
                    aprovada = autorizar(operacao, deepcopy(stable))
                except Exception as error:  # noqa: BLE001 -- falha do juiz bloqueia escrita.
                    aprovada = False
                    logger.warning("juiz de operação indisponível; escrita bloqueada",
                                   extra={"stage": "write_control", "operation": operacao,
                                          "error_type": type(error).__name__})
                if aprovada is not True:
                    results[key] = _NEGADA
                    _somente_leitura.set(True)
                    _gravacao_negada.set(True)
                    logger.info("juiz negou ou não confirmou operação; escrita bloqueada",
                                extra={"stage": "write_control", "operation": operacao})
                    return None
            try:
                result = acao()
            except Exception as error:  # noqa: BLE001 -- resultado de escrita desconhecido exige não repetir.
                # Resultado ambíguo: não repetir a escrita automaticamente.
                results[key] = _INCERTA
                logger.warning("resultado de escrita incerto; repetição bloqueada",
                               extra={"stage": "write_control", "operation": operacao,
                                      "error_type": type(error).__name__})
                return None
            if result is not None and result is not False:
                results[key] = result
                reads = _leituras.get()
                if reads is not None:
                    with reads[1]:
                        reads[0].clear()
            return result
        return None if results[key] is _INCERTA or results[key] is _NEGADA else results[key]
