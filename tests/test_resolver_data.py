"""
A conta de calendário que o modelo errava.

Caso de origem: o usuário pediu churrasco "sabado" e o agente criou o evento
numa sexta. Aqui a data sai do Python, com uma data de hoje fixa para o teste
não depender do dia em que roda.
"""

import json
from datetime import date

import pytest

from app.tools import date_tools


@pytest.fixture(autouse=True)
def hoje_fixo(monkeypatch):
    """Segunda-feira, 5 de outubro de 2026 — o dia do caso real."""

    monkeypatch.setattr(date_tools, "_hoje", lambda: date(2026, 10, 5))


def resolver(referencia, hora=None):
    return json.loads(date_tools.resolver_data.invoke(
        {"referencia": referencia, "hora": hora}
    ))


# --------------------------------------------------------- dia da semana

def test_sabado_nao_vira_sexta():
    """O defeito que originou a ferramenta."""

    r = resolver("sabado")

    assert r["data"] == "2026-10-10"
    assert r["dia_semana"] == "sábado"


@pytest.mark.parametrize(
    ("referencia", "esperado"),
    [
        ("segunda", "2026-10-05"),
        ("terca", "2026-10-06"),
        ("quarta", "2026-10-07"),
        ("quinta", "2026-10-08"),
        ("sexta", "2026-10-09"),
        ("sabado", "2026-10-10"),
        ("domingo", "2026-10-11"),
    ],
)
def test_cada_dia_da_semana(referencia, esperado):
    assert resolver(referencia)["data"] == esperado


def test_dia_de_hoje_e_hoje():
    """"Segunda" dito numa segunda e hoje, nao daqui a sete dias."""

    assert resolver("segunda")["data"] == "2026-10-05"


@pytest.mark.parametrize("referencia", ["sábado", "SABADO", "  sabado  ", "sabado-feira"])
def test_acento_e_caixa_nao_importam(referencia):
    assert resolver(referencia)["data"] == "2026-10-10"


def test_terca_feira_com_sufixo():
    assert resolver("terça-feira")["data"] == "2026-10-06"


# ------------------------------------------------------- semana seguinte

@pytest.mark.parametrize(
    "referencia",
    ["proxima terca", "próxima terça", "terca que vem", "terca seguinte"],
)
def test_semana_que_vem_soma_sete(referencia):
    assert resolver(referencia)["data"] == "2026-10-13"


def test_sabado_que_vem():
    assert resolver("sabado que vem")["data"] == "2026-10-17"


# ------------------------------------------------------------ relativos

@pytest.mark.parametrize(
    ("referencia", "esperado"),
    [
        ("hoje", "2026-10-05"),
        ("amanha", "2026-10-06"),
        ("amanhã", "2026-10-06"),
        ("depois de amanha", "2026-10-07"),
        ("ontem", "2026-10-04"),
    ],
)
def test_referencia_relativa(referencia, esperado):
    assert resolver(referencia)["data"] == esperado


# ----------------------------------------------------------- dia do mes

def test_dia_do_mes_a_frente():
    assert resolver("dia 20")["data"] == "2026-10-20"


def test_dia_do_mes_ja_passou_cai_no_mes_seguinte():
    assert resolver("dia 2")["data"] == "2026-11-02"


def test_dia_31_de_mes_que_tem_31():
    assert resolver("dia 31")["data"] == "2026-10-31"


# -------------------------------------------------------- data explicita

@pytest.mark.parametrize(
    ("referencia", "esperado"),
    [
        ("2026-10-10", "2026-10-10"),
        ("10/10/2026", "2026-10-10"),
        ("10-10-2026", "2026-10-10"),
    ],
)
def test_data_explicita_passa_direto(referencia, esperado):
    assert resolver(referencia)["data"] == esperado


# ------------------------------------------------------------------ hora

def test_hora_entra_no_inicio():
    r = resolver("sabado", "12h")

    assert r["inicio"] == "2026-10-10T12:00:00"


@pytest.mark.parametrize("hora", ["12:30", "12h30"])
def test_hora_com_minuto(hora):
    assert resolver("sabado", hora)["inicio"] == "2026-10-10T12:30:00"


def test_sem_hora_nao_tem_inicio():
    assert "inicio" not in resolver("sabado")


@pytest.mark.parametrize("hora", ["25h", "abc", ""])
def test_hora_invalida_e_ignorada_sem_quebrar(hora):
    r = resolver("sabado", hora)

    assert r["data"] == "2026-10-10"
    assert "inicio" not in r


# ----------------------------------------------------------------- erro

@pytest.mark.parametrize(
    "referencia",
    ["semana que vem", "qualquer coisa", "", "   ", "no feriado"],
)
def test_referencia_irreconhecivel_pede_a_data(referencia):
    """Nunca adivinhar: o agente tem que perguntar."""

    r = resolver(referencia)

    assert "erro" in r
    assert "data" not in r


def test_hoje_vem_na_resposta_para_o_agente_conferir():
    assert resolver("sabado")["hoje"] == "2026-10-05"
