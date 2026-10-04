"""
O que o cliente recebe quando algo sai errado.

Nenhuma falha de infra deve chegar ao mobile como "Internal Server Error" sem
pista: cota esgotada, rede fora e recusa do provedor tem status proprio, e o
resto sai como JSON com o tipo do erro, nunca com o traceback.

Nada aqui chama LLM, banco ou rede.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIConnectionError, APIStatusError, RateLimitError

from app.app import app
from app.auth.dependencies import get_current_user
from app.controller import chat as chat_controller
from app.model.dto.chat_request import LIMITE_MENSAGEM

PEDIDO = {"mensagem": "Tenho arroz em casa?", "household_account_id": 1}


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1}

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


def _resposta(status):
    return httpx.Response(
        status,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )


def _levantar(excecao):
    def falso(**kwargs):
        raise excecao

    return falso


# ------------------------------------------------------- entrada invalida

@pytest.mark.parametrize(
    "corpo",
    [
        {"mensagem": "", "household_account_id": 1},
        {"mensagem": "x" * (LIMITE_MENSAGEM + 1), "household_account_id": 1},
        {"mensagem": "oi", "household_account_id": 0},
        {"household_account_id": 1},
    ],
)
def test_pedido_invalido_e_recusado_sem_chamar_o_modelo(cliente, corpo, monkeypatch):
    """Mensagem gigante nao pode chegar ao modelo: estoura contexto e cota."""

    chamou = []
    monkeypatch.setattr(
        chat_controller,
        "executar_chat",
        lambda **kw: chamou.append(kw),
    )

    resposta = cliente.post("/chat/", json=corpo)

    assert resposta.status_code == 422
    assert chamou == []


# --------------------------------------------------------- falhas do groq

def test_cota_esgotada_vira_429_com_motivo(cliente, monkeypatch):
    erro = RateLimitError("limite diario", response=_resposta(429), body=None)
    monkeypatch.setattr(chat_controller, "executar_chat", _levantar(erro))

    resposta = cliente.post("/chat/", json=PEDIDO)

    assert resposta.status_code == 429
    assert resposta.json()["origem"] == "groq"
    assert "limite diario" in resposta.json()["mensagem_do_provedor"]


def test_rede_fora_vira_503(cliente, monkeypatch):
    erro = APIConnectionError(
        request=httpx.Request("POST", "https://api.groq.com"),
    )
    monkeypatch.setattr(chat_controller, "executar_chat", _levantar(erro))

    resposta = cliente.post("/chat/", json=PEDIDO)

    assert resposta.status_code == 503
    assert resposta.json()["origem"] == "groq"


def test_recusa_do_provedor_vira_502(cliente, monkeypatch):
    """400 de schema de ferramenta: culpa do provedor, nao nossa."""

    erro = APIStatusError(
        "tool call validation failed",
        response=_resposta(400),
        body=None,
    )
    monkeypatch.setattr(chat_controller, "executar_chat", _levantar(erro))

    resposta = cliente.post("/chat/", json=PEDIDO)

    assert resposta.status_code == 502
    assert "tool call validation failed" in resposta.json()["mensagem_do_provedor"]


# ------------------------------------------------------ falha inesperada

def test_falha_inesperada_sai_como_json_sem_traceback(cliente, monkeypatch):
    monkeypatch.setattr(
        chat_controller,
        "executar_chat",
        _levantar(RuntimeError("banco caiu no meio")),
    )

    resposta = cliente.post("/chat/", json=PEDIDO)
    corpo = resposta.json()

    assert resposta.status_code == 500
    assert corpo["tipo"] == "RuntimeError"
    assert corpo["origem"] == "ceris-ia"
    assert "banco caiu no meio" not in str(corpo)
    assert "Traceback" not in str(corpo)


def test_resposta_boa_passa_intacta(cliente, monkeypatch):
    monkeypatch.setattr(
        chat_controller,
        "executar_chat",
        lambda **kw: {"resposta": "Sim, voce tem arroz.", "session_id": "abc"},
    )

    resposta = cliente.post("/chat/", json=PEDIDO)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "resposta": "Sim, voce tem arroz.",
        "session_id": "abc",
    }
