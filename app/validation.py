"""Validações de dados de domínio, independentes dos modelos de linguagem."""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation


def validar_titulo(titulo: str) -> str:
    titulo = titulo.strip()
    if not titulo or re.search(r"\[(?:PII_|(?:TELEFONE|CPF|EMAIL) OMITIDO)", titulo, re.IGNORECASE):
        raise ValueError("Informe um título sem dados pessoais ou marcadores de privacidade.")
    return titulo


def _normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                   if not unicodedata.combining(c))


def ingredientes_basicos_ausentes(ingredientes: list[dict], instrucoes: str) -> list[str]:
    """Detecta omissões comuns; não inventa quantidades nem valida toda a culinária."""
    nomes = " ".join(str(i.get("name") or i.get("nome") or i.get("ingrediente") or "")
                     for i in ingredientes if isinstance(i, dict))
    nomes, preparo = _normalizar(nomes), _normalizar(instrucoes)
    # Mencionar uma restrição no preparo não significa usar o ingrediente.
    preparo = re.sub(r"\bsem\s+(?:agua|sal|azeite|oleo|manteiga|acucar|leite)\b", "", preparo)
    preparo = re.sub(r"\bnao\s+(?:use|adicione|acrescente|coloque)\b[^.!?\n]*", "", preparo)
    basicos = {"água": r"\bagua\b", "sal": r"\bsal\b", "azeite": r"\bazeite\b",
               "óleo": r"\boleo\b", "manteiga": r"\bmanteiga\b", "açúcar": r"\bacucar\b",
               "leite": r"\bleite\b"}
    # Água para lavar utensílios/alimentos não é ingrediente. A checagem
    # aplica-se apenas a água explicitamente adicionada ao prato.
    agua_no_prato = bool(re.search(
        r"\b(?:adicione|acrescente|junte|despeje|coloque)\b[^.!?\n]*\bagua\b", preparo))
    return [nome for nome, padrao in basicos.items()
            if re.search(padrao, preparo) and not re.search(padrao, nomes)
            and (nome != "água" or agua_no_prato)]



def inteiro_positivo(valor: int, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(f"{campo} deve ser um inteiro positivo.")
    return valor


def validar_evento(data: datetime, duracao: int, qtd_pessoas: int,
                   descricao: str, local: str) -> None:
    if not isinstance(data, datetime):
        raise TypeError("Informe uma data valida para o evento.")
    inteiro_positivo(duracao, "Duracao")
    inteiro_positivo(qtd_pessoas, "Numero de participantes")
    if not isinstance(descricao, str) or not descricao.strip():
        raise ValueError("Informe a descricao do evento.")
    if not isinstance(local, str) or not local.strip():
        raise ValueError("Informe o local do evento.")


_UNIDADES_RECEITA = re.compile(
    r"(?:g|gr|gramas?|kg|quilos?|quilogramas?|mg|miligramas?|ml|mililitros?|"
    r"l|litros?|un|unid|unidades?|unids|xicaras?(?:\s*(?:\(cha\)|de cha))?|"
    r"colher(?:es)?(?:\s*(?:de\s+)?(?:sopa|cha|cafe)|\s*\((?:sopa|cha|cafe)\))?|"
    r"pitadas?|dentes?|fatias?|ramos?|folhas?|latas?|pacotes?|saches?|copos?|"
    r"punhados?|tabletes?|potes?|garrafas?|pequenas?|medias?|grandes?)"
    r"(?:\s+(?:rasas?|cheias?))?"
)
_FRACOES = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3",
            "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}


def validar_quantidade_receita(valor, unidade: str = "") -> str:
    """Valida medidas culinarias sem estimar conversao para massa ou volume."""
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float, Decimal)):
        raise TypeError("Informe uma quantidade culinaria valida.")
    texto = str(valor).strip()
    if unidade:
        if not isinstance(unidade, str):
            raise ValueError("Informe uma unidade valida.")
        # Campo separado so complementa numeros sem unidade.
        if re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", texto):
            texto += " " + unidade.strip()
    normal = _normalizar(texto)
    if normal in {"a gosto", "quanto baste", "q.b.", "qb"}:
        return texto
    texto_numerico = texto
    for simbolo, fracao in _FRACOES.items():
        texto_numerico = texto_numerico.replace(simbolo, " " + fracao)
    normal = _normalizar(texto_numerico).strip()
    match = re.fullmatch(
        r"(?P<numero>[0-9]+(?:[.,][0-9]+)?(?:\s+[0-9]+\s*/\s*[0-9]+)?|[0-9]+\s*/\s*[0-9]+)"
        r"\s*(?P<unidade>[^0-9]+)", normal)
    if not match or not _UNIDADES_RECEITA.fullmatch(match["unidade"].strip()):
        raise ValueError("Informe quantidade positiva e unidade reconhecida, ou 'a gosto'.")
    try:
        numero = match["numero"].strip()
        if "/" in numero:
            # Normalize optional spaces around slash before splitting mixed fractions.
            numero = re.sub(r"\s*/\s*", "/", numero)
            partes = numero.split()
            fracao = partes[-1].split("/")
            resultado = Decimal(fracao[0]) / Decimal(fracao[1])
            if len(partes) == 2:
                resultado += Decimal(partes[0])
        else:
            resultado = Decimal(numero.replace(",", "."))
        if not resultado.is_finite() or resultado <= 0:
            raise ValueError("A quantidade deve ser finita e positiva.")
    except (InvalidOperation, ZeroDivisionError):
        raise ValueError("Informe uma fracao valida com denominador positivo.") from None
    return texto
