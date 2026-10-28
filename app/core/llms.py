"""
Clientes de LLM, um por tipo de trabalho — não um por papel.

O maior gasto de saída não é o texto, é o raciocínio que o modelo produz antes
dele e descarta. Medido com os prompts reais, padrão contra RACIOCINIO_CURTO:

    papel          raciocínio   com corte   texto útil
    roteador           43           19          11
    seletor            75           24          13
    juiz               74           22          22
    orquestrador      555            6          43

Quem segue roteiro e devolve pouco texto não melhora com raciocínio longo: as
respostas saem idênticas nos dois níveis. Os agentes ficam de fora, porque lá
o raciocínio escolhe ferramenta e monta JSON — cortar é cortar o trabalho.

Sobre max_tokens: o teto cobre raciocínio MAIS texto. Teto curto faz o modelo
gastar tudo pensando e devolver conteúdo VAZIO, com finish_reason "length" e
nenhum erro. Os tetos aqui têm ~8x de folga sobre o medido: são freio contra
disparada, não economia. A economia vem do nível de raciocínio.

Trocando de provedor, confira três coisas: os níveis aceitos em
reasoning_effort, se o modelo aceita temperature diferente do padrão (vários
de raciocínio não aceitam) e se o teto se chama max_tokens ou
max_completion_tokens.
"""

import httpx

from ..config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    LLM_FALLBACK_PROVIDERS,
    LLM_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
)
from .provider_policy import TransientFallback

MODELO_PADRAO = {
    "groq": "openai/gpt-oss-20b",
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-6-luna",
}

if LLM_PROVIDER not in MODELO_PADRAO:
    raise RuntimeError(
        f"LLM_PROVIDER '{LLM_PROVIDER}' invalido. Use: {', '.join(MODELO_PADRAO)}."
    )

PROVEDOR = LLM_PROVIDER
MODELO = LLM_MODEL or MODELO_PADRAO[PROVEDOR]

_CHAVE = {"groq": GROQ_API_KEY, "gemini": GEMINI_API_KEY, "openai": OPENAI_API_KEY}

# Reserva: outro provedor, com chave configurada. Sem isso, fica sem reserva.
RESERVAS = tuple(
    provider
    for provider in LLM_FALLBACK_PROVIDERS
    if provider in MODELO_PADRAO
    and provider != PROVEDOR
    and _CHAVE.get(provider)
)

# Sem retry no SDK: a política faz no máximo uma troca transitória de provedor.
# Evita multiplicar esperas entre SDK, fallback, agente e juiz.
TENTATIVAS = 0
TIMEOUT_S = 30

# Única escolha que reduz: "medium" devolve o mesmo que o padrão.
RACIOCINIO_CURTO = "low"

# Fixa a amostragem para que duas execuções iguais deem o mesmo resultado. Sem
# isso, comparar antes e depois de uma mudança vira leitura de ruído.
SEMENTE = 42

# Medidos no Groq. O Gemini raciocina mais antes de responder e, com 300, as
# vezes gastava o teto todo pensando: o roteador voltava vazio e um pedido de
# receita caia no fallback. Teto e freio, nao economia (ver acima).
TETO_ESCOLHA = 2048
TETO_VEREDITO = 2048

_openai_http_client = None
_openai_async_client = None


def _cliente(
    temperatura: float,
    raciocinio: str | None = None,
    teto: int | None = None,
    semente: int | None = SEMENTE,
    timeout: int = TIMEOUT_S,
    tentativas: int = TENTATIVAS,
    provedor: str = PROVEDOR,
):
    modelo = MODELO if provedor == PROVEDOR else MODELO_PADRAO[provedor]

    if provedor == "gemini":
        return _cliente_gemini(
            temperatura, raciocinio, teto, semente, timeout, tentativas, modelo,
        )

    if provedor == "openai":
        return _cliente_openai(
            temperatura, teto, semente, timeout, tentativas, modelo,
        )

    from langchain_groq import ChatGroq

    extras = {}

    if raciocinio:
        extras["reasoning_effort"] = raciocinio

    if teto:
        extras["max_tokens"] = teto

    # Direto em model_kwargs: passada solta, a langchain move para la de
    # qualquer forma e ainda avisa no import.
    if semente is not None:
        extras["model_kwargs"] = {"seed": semente}

    return ChatGroq(
        model=modelo,
        temperature=temperatura,
        api_key=GROQ_API_KEY,
        max_retries=tentativas,
        request_timeout=timeout,
        **extras,
    )


def _cliente_openai(
    temperatura: float,
    teto: int | None,
    semente: int | None,
    timeout: int,
    tentativas: int,
    modelo: str,
):
    """Cliente econômico com tool calling compatível no Chat Completions."""

    global _openai_async_client, _openai_http_client

    from langchain_openai import ChatOpenAI

    if _openai_http_client is None:
        # Compartilhar o transporte evita criar um pool TLS por papel do grafo
        # e reduz bastante o tempo de inicialização, sobretudo no Windows.
        _openai_http_client = httpx.Client()
        _openai_async_client = httpx.AsyncClient()

    extras = {}
    if teto:
        extras["max_completion_tokens"] = teto
    if semente is not None:
        extras["seed"] = semente

    return ChatOpenAI(
        model=modelo,
        temperature=temperatura,
        api_key=OPENAI_API_KEY,
        max_retries=tentativas,
        timeout=timeout,
        http_client=_openai_http_client,
        http_async_client=_openai_async_client,
        # O GPT-6 Luna exige reasoning_effort=none para function calling no
        # endpoint Chat Completions usado pelo create_agent.
        reasoning_effort="none",
        **extras,
    )


def _cliente_gemini(
    temperatura: float,
    raciocinio: str | None,
    teto: int | None,
    semente: int | None,
    timeout: int,
    tentativas: int,
    modelo: str,
):
    """
    Mesmo papel do cliente Groq. O Gemini chama o nivel de raciocinio de
    thinking_level e o teto de max_output_tokens.
    """

    from langchain_google_genai import ChatGoogleGenerativeAI

    extras = {}

    if raciocinio:
        extras["thinking_level"] = raciocinio

    if teto:
        extras["max_output_tokens"] = teto

    if semente is not None:
        extras["seed"] = semente

    return ChatGoogleGenerativeAI(
        model=modelo,
        temperature=temperatura,
        google_api_key=GEMINI_API_KEY,
        max_retries=tentativas,
        timeout=timeout,
        **extras,
    )


def texto(resposta) -> str:
    """
    Texto de uma resposta do modelo, qualquer que seja o provedor.

    O Groq devolve `content` como string. O Gemini 3 devolve uma lista de
    blocos ({"type": "text", "text": ...}, raciocinio, assinaturas), e quem
    chamava `.content.strip()` ou `.splitlines()` quebrava com AttributeError.
    """

    conteudo = getattr(resposta, "content", resposta)

    if conteudo is None:
        return ""

    if isinstance(conteudo, str):
        return conteudo

    if isinstance(conteudo, list):
        partes = []

        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(bloco.get("text", ""))

        return "".join(partes)

    return str(conteudo)


def _reservas(*args, **kwargs):
    """Clientes de reserva na ordem configurada, ignorando chaves ausentes."""

    return [_cliente(*args, provedor=provider, **kwargs) for provider in RESERVAS]


def _com_reserva(*args, **kwargs):
    """
    Cliente do provedor principal que, se falhar, refaz a chamada na reserva.

    So para chamadas diretas (invoke). Agente com ferramentas precisa do
    modelo puro: a reserva dele entra pelo middleware, em agents.py.
    """

    principal = _cliente(*args, **kwargs)
    reservas = _reservas(*args, **kwargs)

    return TransientFallback(principal, reservas)


# Devolve uma palavra: nome de rota ou de skill.
escolha_llm = _com_reserva(0, RACIOCINIO_CURTO, TETO_ESCOLHA, timeout=12)

# Guardrails usam revisão curta. Gemini exige deadline mínimo de 10 segundos.
# O juiz Jev usa seu próprio cliente; sua escalada LLM não tem retry do SDK.
JUIZ_TIMEOUT_S = 12
JUIZ_TENTATIVAS = 0

revisao_llm = _com_reserva(
    0, RACIOCINIO_CURTO, TETO_VEREDITO,
    timeout=JUIZ_TIMEOUT_S, tentativas=JUIZ_TENTATIVAS,
)

# Escreve texto para a pessoa ler, de tamanho variável: sem teto.
texto_llm = _com_reserva(0, RACIOCINIO_CURTO, timeout=15)

# Agentes: raciocínio curto com margem de saída para receita estruturada.
specialist_llm = _cliente(0.4, RACIOCINIO_CURTO, 8192)
specialist_reserva = _reservas(0.4, RACIOCINIO_CURTO, 8192)

# Estoque e consulta e remocao, nao criacao: nao ganha com variedade nem com
# raciocinio longo. Medido: com o raciocinio padrao o agente gastou 2048 tokens
# pensando e devolveu resposta vazia, e cada mensagem passava de 10 mil tokens,
# acima dos 8 mil por minuto do plano do Groq, o que gera 429 e 12 a 26s de
# espera. Raciocinio curto e teto cortam isso na origem.
TETO_ESTOQUE = 1200

estoque_llm = _cliente(0, RACIOCINIO_CURTO, TETO_ESTOQUE)
estoque_reserva = _reservas(0, RACIOCINIO_CURTO, TETO_ESTOQUE)

# Instância legada mantida para comparativos e compatibilidade dos testes.
# O fluxo de produção não faz segunda opinião nem chama este cliente.
revisao_segunda_llm = _com_reserva(
    0, RACIOCINIO_CURTO, TETO_VEREDITO, semente=20261010,
    timeout=JUIZ_TIMEOUT_S, tentativas=JUIZ_TENTATIVAS,
)

# Apelidos por papel. Apontam para a mesma instância enquanto a configuração
# for a mesma; separar um deles depois é trocar uma linha.
roteador_llm = escolha_llm
seletor_llm = escolha_llm

juiz_llm = _com_reserva(
    0, RACIOCINIO_CURTO, TETO_VEREDITO, timeout=JUIZ_TIMEOUT_S, tentativas=0,
)
guardrail_llm = revisao_llm

orquestrador_llm = texto_llm
memoria_llm = texto_llm

groq_llm = specialist_llm

# Agente de FAQ: modelo puro, porque create_agent precisa ligar as ferramentas
# nele. A reserva entra pelo middleware.
fast_llm = _cliente(0, RACIOCINIO_CURTO)
fast_reserva = _reservas(0, RACIOCINIO_CURTO)
