"""
Prazo de validade de produto sem data, pesquisado na web.

O modelo decidia sozinho se "ja sabia" o prazo e, num teste, pulou a pesquisa e
citou uma fonte que nao existia. Aqui a tool sempre pesquisa. Um modelo leve
escolhe a frase certa entre os trechos (regex sozinho pegava "banana passa"
como banana), e o Python confere que a frase existe na fonte e tira o numero
dela. Sem frase que passe na conferencia, devolve "sem prazo" e o item entra
sem validade.

Chama a API da Tavily direto, sem o MCP: e uma ida HTTP so, e a tool ja
devolve a data pronta, poupando uma volta do modelo com resolver_data.
"""

import json
import logging
import re
import unicodedata
from datetime import timedelta

import httpx
from langchain.tools import tool

from app.config import TAVILY_API_KEY
from app.tools.date_tools import NUMEROS, _hoje

logger = logging.getLogger(__name__)

URL_TAVILY = "https://api.tavily.com/search"
TIMEOUT_S = 10
MAX_RESULTADOS = 6

# Opiniao solta, nao referencia de conservacao.
DOMINIOS_EXCLUIDOS = [
    "reddit.com", "quora.com", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com", "x.com", "twitter.com", "pinterest.com",
]

# Faixa vira o limite de baixo, que e o lado seguro ("tres a sete dias" = 3).
# Mais larga que isto ("1 a 6 meses") ja nao diz nada.
RAZAO_MAXIMA_FAIXA = 3.0

# A frase precisa citar onde o produto fica: "30 dias" numa tabela de
# congelados nao vale para a geladeira.
PALAVRAS_DA_GUARDA = {
    "geladeira": ("geladeira", "refrigerad", "refrigerador"),
    "temperatura ambiente": ("ambiente", "fora da geladeira", "despensa"),
    "congelador": ("congel", "freezer"),
}

DIAS_POR_UNIDADE = {"dia": 1, "semana": 7, "mes": 30, "ano": 365}

_NUMERO = r"(\d{1,3}(?:[.,]\d)?|" + "|".join(sorted(NUMEROS, key=len, reverse=True)) + r")"
_UNIDADE = r"(dias?|semanas?|mes|meses|anos?)"

_FAIXA = re.compile(r"\b" + _NUMERO + r"\s*(?:a|ate|-|–|ou)\s*" + _NUMERO + r"\s+" + _UNIDADE + r"\b")
_UNICO = re.compile(r"\b" + _NUMERO + r"\s+" + _UNIDADE + r"\b")


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")


def _numero(bruto: str) -> float:
    bruto = bruto.replace(",", ".")
    return float(bruto) if bruto[0].isdigit() else float(NUMEROS[bruto])


def _unidade_em_dias(unidade: str) -> int:
    for raiz, dias in DIAS_POR_UNIDADE.items():
        if unidade.startswith(raiz):
            return dias
    raise ValueError(unidade)


def _palavras(texto: str) -> set[str]:
    """Sem o "s" final: "maçãs" e "maçã" sao a mesma palavra para o casamento."""

    return {
        p.removesuffix("s")
        for p in re.split(r"[^a-z0-9]+", _normalizar(texto))
        if len(p) >= 3
    }


def _prazos_da_frase(frase: str) -> list[tuple[int, int | None]]:
    """(posicao, dias) de cada prazo da frase; dias None para faixa larga demais."""

    prazos = []
    ocupado = []

    for faixa in _FAIXA.finditer(frase):
        menor, maior = sorted((_numero(faixa.group(1)), _numero(faixa.group(2))))
        valido = menor > 0 and maior / menor <= RAZAO_MAXIMA_FAIXA
        dias = round(menor * _unidade_em_dias(faixa.group(3))) if valido else None
        prazos.append((faixa.start(), dias))
        ocupado.append(range(faixa.start(), faixa.end()))

    for unico in _UNICO.finditer(frase):
        # O "quatro semanas" de "tres a quatro semanas" ja foi lido como faixa.
        if any(unico.start() in trecho for trecho in ocupado):
            continue
        valor = _numero(unico.group(1))
        prazos.append((unico.start(), round(valor * _unidade_em_dias(unico.group(2))) if valor > 0 else None))

    return prazos


def _prazo_na_frase(frase: str, chaves_guarda: tuple[str, ...] = ()) -> int | None:
    """
    Com mais de um prazo na frase ("uma semana fora e tres a quatro semanas na
    geladeira"), vale o mais perto da palavra do local pedido.
    """

    prazos = _prazos_da_frase(frase)
    if not prazos:
        return None

    # Primeiro por oracao: "uma semana em temperatura ambiente | e tres a
    # quatro semanas na geladeira". A oracao que cita o local e tem prazo manda.
    if chaves_guarda:
        for oracao in re.split(r",|;| e | mas | enquanto | ja ", frase):
            if any(chave in oracao for chave in chaves_guarda):
                da_oracao = _prazos_da_frase(oracao)
                if da_oracao:
                    return da_oracao[0][1]

    # Local e prazo em oracoes separadas ("na geladeira, dura 4 semanas"):
    # vale o prazo mais perto do local.
    posicoes_guarda = [m.start() for chave in chaves_guarda for m in re.finditer(re.escape(chave), frase)]

    if posicoes_guarda:
        _, dias = min(prazos, key=lambda p: min(abs(p[0] - g) for g in posicoes_guarda))
    else:
        _, dias = prazos[0]

    return dias


def prazo_no_trecho(trecho: str, produto: str, guarda: str | None = None) -> int | None:
    """
    Prazo em dias da primeira frase que cita o produto e o local de guarda.

    Por frase, e nao pelo trecho inteiro: em tabela de varios alimentos o
    primeiro numero quase nunca e do produto pedido. Funcao pura, para os
    testes cobrirem a regra sem rede.
    """

    produto_palavras = _palavras(produto)
    chaves_guarda = PALAVRAS_DA_GUARDA.get(_normalizar(guarda or ""), ())

    for frase in re.split(r"(?<=[.!?;])\s+|\n+", _normalizar(trecho)):
        if not produto_palavras & _palavras(frase):
            continue
        if chaves_guarda and not any(chave in frase for chave in chaves_guarda):
            continue

        prazo = _prazo_na_frase(frase, chaves_guarda)
        if prazo is not None:
            return prazo

    return None


SEM_PRAZO = {"dias": None, "motivo": "nenhuma fonte deu um prazo seguro para esse produto"}

LEITOR_PROMPT = """Você recebe trechos de páginas da web numerados.
Escolha UMA frase que diga quanto tempo dura o produto pedido, do jeito que a
pessoa comprou (in natura, inteiro, fechado), guardado no local pedido.

Não serve frase sobre derivado ou preparo (passa, doce, extrato, polpa, suco,
cozido, cortado, aberto, congelado quando o local é outro), a menos que o
produto pedido seja exatamente esse. Não serve tabela que mistura vários
alimentos sem deixar claro qual prazo é de qual.

Copie a frase LITERALMENTE, sem corrigir nada.
Responda só com JSON: {"indice": <número do trecho>, "frase": "<frase>"}
Se nenhuma frase servir: {"indice": null}"""

TRECHO_MAXIMO = 900


def _sem_espacos_extras(texto: str) -> str:
    return re.sub(r"\s+", " ", _normalizar(texto)).strip()


def validar_escolha(resultados: list[dict], produto: str, guarda: str, escolha: dict) -> dict:
    """
    Confere o que o modelo escolheu. Funcao pura, testada sem rede.

    A frase precisa existir de verdade naquele trecho e citar o produto e o
    local de guarda; o prazo sai da frase pelo parser, nunca do modelo. Assim
    ele escolhe, mas nao inventa nem fonte nem numero.
    """

    indice = escolha.get("indice")
    frase = escolha.get("frase") or ""

    if not isinstance(indice, int) or not 0 <= indice < len(resultados) or not frase:
        return SEM_PRAZO

    conteudo = resultados[indice].get("content", "")[:TRECHO_MAXIMO]

    if _sem_espacos_extras(frase) not in _sem_espacos_extras(conteudo):
        return SEM_PRAZO

    dias = prazo_no_trecho(frase, produto, guarda)
    if dias is None:
        return SEM_PRAZO

    return {"dias": dias, "fonte": resultados[indice].get("url", ""), "trecho": frase.strip()}


def _escolha_do_modelo(resultados: list[dict], produto: str, guarda: str) -> dict:
    # Import tardio: o cliente do modelo nao e necessario para os testes puros.
    from app.core.llms import revisao_llm

    trechos = "\n\n".join(
        f"[{i}] {r.get('url', '')}\n{r.get('content', '')[:TRECHO_MAXIMO]}"
        for i, r in enumerate(resultados)
    )

    resposta = revisao_llm.invoke([
        ("system", LEITOR_PROMPT),
        ("human", f"Produto: {produto}\nLocal: {guarda}\n\nTrechos:\n{trechos}"),
    ])

    achado = re.search(r"\{.*\}", str(resposta.content), re.DOTALL)
    if achado is None:
        return {}

    try:
        return json.loads(achado.group(0))
    except json.JSONDecodeError:
        return {}


def _pesquisar(consulta: str) -> list[dict]:
    resposta = httpx.post(
        URL_TAVILY,
        json={
            "api_key": TAVILY_API_KEY,
            "query": consulta,
            "search_depth": "basic",
            "max_results": MAX_RESULTADOS,
            "exclude_domains": DOMINIOS_EXCLUIDOS,
        },
        timeout=TIMEOUT_S,
    )
    resposta.raise_for_status()
    return resposta.json().get("results", [])


@tool("estimar_validade")
def estimar_validade(produto: str, guarda: str = "geladeira") -> str:
    """
    Estima a validade de um produto que não tem data, pesquisando na web.

    Use SEMPRE que o produto não tiver data informada e não vier de nota
    fiscal. Não estime de cabeça.

    Parâmetros:
        - produto: nome do produto, como a pessoa falou ("maçã").
        - guarda: onde fica guardado: "geladeira", "temperatura ambiente"
          ou "congelador".

    Devolve JSON com "dias", "validade" (AAAA-MM-DD) e "fonte"; ou "dias"
    nulo e "motivo" quando não há prazo seguro — aí registre sem validade.
    """

    if not TAVILY_API_KEY:
        return json.dumps({"dias": None, "motivo": "pesquisa indisponivel"}, ensure_ascii=False)

    try:
        resultados = _pesquisar(f"quanto tempo dura {produto} na {guarda} prazo de validade")
    except httpx.HTTPError:
        logger.exception("pesquisa de validade falhou")
        return json.dumps({"dias": None, "motivo": "pesquisa indisponivel"}, ensure_ascii=False)

    if not resultados:
        return json.dumps(SEM_PRAZO, ensure_ascii=False)

    try:
        escolha = validar_escolha(
            resultados, produto, guarda, _escolha_do_modelo(resultados, produto, guarda)
        )
    except Exception:
        # Modelo fora do ar ou estourou o tempo: sem prazo, nunca chute.
        logger.exception("leitura do prazo falhou")
        escolha = SEM_PRAZO

    escolha = dict(escolha)

    if escolha["dias"] is not None:
        escolha["validade"] = (_hoje() + timedelta(days=escolha["dias"])).isoformat()
        escolha["guarda"] = guarda

    return json.dumps(escolha, ensure_ascii=False)
