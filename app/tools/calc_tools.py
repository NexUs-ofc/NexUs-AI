"""
Cálculo por ferramenta, não pelo modelo.

Aritmética é onde o LLM mais erra, e erra com confiança: soma de lista longa,
escala de porção, percentual de conclusão. Aqui o número sai do numpy, e o
agente só repassa.

As três devolvem JSON como as demais ferramentas do projeto.
"""

import json

import numpy as np
from langchain.tools import tool


def _numeros(valores: list[float]) -> np.ndarray:
    return np.array(valores, dtype=float)


@tool("somar_valores")
def somar_valores(valores: list[float]) -> str:
    """
    Soma uma lista de números e devolve também média, maior e menor.

    Use SEMPRE que precisar totalizar: preço de itens de uma lista, quantidades
    de estoque, porções. Nunca some de cabeça.

    Parâmetros:
        - valores: Lista de números. Ex: [14.90, 8.50, 12.99]
    """

    if not valores:
        return json.dumps({"erro": "Lista vazia."}, ensure_ascii=False)

    dados = _numeros(valores)

    return json.dumps(
        {
            "soma": round(float(np.sum(dados)), 2),
            "media": round(float(np.mean(dados)), 2),
            "maior": round(float(np.max(dados)), 2),
            "menor": round(float(np.min(dados)), 2),
            "quantidade": int(dados.size),
        },
        ensure_ascii=False,
    )


@tool("escalar_quantidades")
def escalar_quantidades(
    quantidades: list[float],
    porcoes_origem: int,
    porcoes_destino: int,
) -> str:
    """
    Reescala quantidades de uma receita de um número de porções para outro.

    Use SEMPRE que adaptar receita para outra quantidade de pessoas, em vez de
    multiplicar mentalmente.

    Parâmetros:
        - quantidades: Quantidades na receita original. Ex: [500, 200, 1]
        - porcoes_origem: Para quantas porções a receita original serve.
        - porcoes_destino: Para quantas porções você precisa.
    """

    if porcoes_origem <= 0:
        return json.dumps(
            {"erro": "porcoes_origem tem que ser maior que zero."},
            ensure_ascii=False,
        )

    fator = porcoes_destino / porcoes_origem
    escaladas = _numeros(quantidades) * fator

    return json.dumps(
        {
            "fator": round(fator, 4),
            "quantidades": [round(float(q), 2) for q in escaladas],
        },
        ensure_ascii=False,
    )


@tool("calcular_percentual")
def calcular_percentual(parte: float, total: float) -> str:
    """
    Percentual de uma parte sobre um total, arredondado para inteiro.

    Use para progresso de lista de compras, proporção de estoque consumido e
    qualquer "X de Y" que vire porcentagem na resposta.

    Parâmetros:
        - parte: Valor da parte. Ex: 3
        - total: Valor do total. Ex: 7
    """

    if total == 0:
        return json.dumps({"percentual": 0, "parte": parte, "total": total},
                          ensure_ascii=False)

    percentual = round(float(np.divide(parte, total)) * 100)

    return json.dumps(
        {"percentual": percentual, "parte": parte, "total": total},
        ensure_ascii=False,
    )
