"""Padroes compartilhados de dados pessoais em claro na saida."""

import re

# A ordem importa: o primeiro padrao que casar leva o trecho. CPF vinha antes
# e o padrao dele casa 11 digitos seguidos, entao todo telefone de celular
# saia rotulado como CPF. Agora o telefone, que exige a forma de telefone (DDD
# e separador), e testado primeiro; o CPF so pega o que sobrar.
PII = [
    ("TELEFONE", r"(?<!\w)(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}(?!\w)"),
    ("CPF",      r"(?<!\w)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\w)"),
    ("EMAIL",    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
]


def contem_dado_pessoal(texto: str) -> bool:
    return any(re.search(padrao, texto) for _, padrao in PII)
