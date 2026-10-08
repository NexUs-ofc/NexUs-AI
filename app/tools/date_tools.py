"""
Data por ferramenta, não pela cabeça do modelo.

"Sábado" virou sexta num evento real: o modelo contou o dia da semana sozinho e
errou em um dia. Contar calendário é como somar lista longa — ele faz, e faz
com confiança. Aqui a conta sai do Python.
"""

import json
import re
from datetime import date, datetime, timedelta

from langchain.tools import tool

DIAS = {
    "segunda": 0, "segunda-feira": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sabado": 5, "sábado": 5,
    "domingo": 6,
}

NOMES = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)

RELATIVOS = {
    "hoje": 0,
    "amanha": 1, "amanhã": 1,
    "depois de amanha": 2, "depois de amanhã": 2,
    "ontem": -1,
}


def _hoje() -> date:
    return datetime.now().astimezone().date()


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.strip().lower())


def _data_explicita(texto: str) -> date | None:
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()  # noqa: DTZ007
        except ValueError:
            continue

    return None


def _proximo_dia_da_semana(alvo: int, hoje: date, semana_seguinte: bool) -> date:
    # 0 quando hoje já é o dia pedido: "sábado" dito num sábado é hoje.
    avanco = (alvo - hoje.weekday()) % 7

    if semana_seguinte:
        avanco += 7

    return hoje + timedelta(days=avanco)


def _resolver(referencia: str, hoje: date) -> date | None:
    texto = _limpar(referencia)

    explicita = _data_explicita(texto)
    if explicita is not None:
        return explicita

    for chave, deslocamento in RELATIVOS.items():
        if texto == chave:
            return hoje + timedelta(days=deslocamento)

    semana_seguinte = bool(
        re.search(r"\b(que vem|seguinte|pr[óo]xim[ao])\b", texto)
    )

    for nome, indice in DIAS.items():
        if re.search(rf"\b{re.escape(nome)}\b", texto):
            return _proximo_dia_da_semana(indice, hoje, semana_seguinte)

    dia = re.search(r"\bdia (\d{1,2})\b", texto)
    if dia:
        numero = int(dia.group(1))

        if not 1 <= numero <= 31:
            return None

        try:
            candidato = hoje.replace(day=numero)
        except ValueError:
            return None

        if candidato < hoje:
            mes = hoje.month + 1
            ano = hoje.year + (mes > 12)
            mes = 1 if mes > 12 else mes

            try:
                candidato = date(ano, mes, numero)
            except ValueError:
                return None

        return candidato

    return None


def _hora(texto: str | None) -> tuple[int, int] | None:
    if not texto:
        return None

    achado = re.search(r"(\d{1,2})\s*(?::|h)\s*(\d{2})?", str(texto))

    if not achado:
        return None

    horas = int(achado.group(1))
    minutos = int(achado.group(2) or 0)

    if not (0 <= horas <= 23 and 0 <= minutos <= 59):
        return None

    return horas, minutos


@tool("resolver_data")
def resolver_data(referencia: str, hora: str | None = None) -> str:
    """
    Converte uma referência de data em linguagem natural na data real.

    Use SEMPRE que o usuário falar de um dia sem dar a data completa: "sábado",
    "amanhã", "semana que vem", "próxima terça", "dia 20". NUNCA conte o dia da
    semana de cabeça — é onde o erro de um dia aparece.

    Parâmetros:
        - referencia: O que o usuário disse. Ex: "sabado", "amanha", "dia 20",
          "proxima terca", "25/10/2026".
        - hora: Hora do dia, quando o usuário informar. Ex: "12h", "12:30".

    Retorno:
        {"data": "2026-10-10", "dia_semana": "sábado",
         "inicio": "2026-10-10T12:00:00"}
        ou {"erro": "..."} quando a referência não é reconhecida — nesse caso
        pergunte a data ao usuário, não adivinhe.
    """

    hoje = _hoje()
    resolvida = _resolver(referencia, hoje)

    if resolvida is None:
        return json.dumps(
            {"erro": f"Não reconheci a data em '{referencia}'. Pergunte o dia ao usuário."},
            ensure_ascii=False,
        )

    saida = {
        "data": resolvida.isoformat(),
        "dia_semana": NOMES[resolvida.weekday()],
        "hoje": hoje.isoformat(),
    }

    marcada = _hora(hora)

    if marcada is not None:
        # Naive de proposito: e o que as ferramentas de evento gravam.
        saida["inicio"] = datetime(  # noqa: DTZ001
            resolvida.year, resolvida.month, resolvida.day,
            marcada[0], marcada[1],
        ).isoformat()

    return json.dumps(saida, ensure_ascii=False)
