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

from ..config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    LLM_FALLBACK_PROVIDER,
    LLM_MODEL,
    LLM_PROVIDER,
)

MODELO_PADRAO = {
    "groq": "openai/gpt-oss-20b",
    "gemini": "gemini-3.5-flash-lite",
}

if LLM_PROVIDER not in MODELO_PADRAO:
    raise RuntimeError(
        f"LLM_PROVIDER '{LLM_PROVIDER}' invalido. Use: {', '.join(MODELO_PADRAO)}."
    )

PROVEDOR = LLM_PROVIDER
MODELO = LLM_MODEL or MODELO_PADRAO[PROVEDOR]

_CHAVE = {"groq": GROQ_API_KEY, "gemini": GEMINI_API_KEY}

# Reserva: outro provedor, com chave configurada. Sem isso, fica sem reserva.
RESERVA = (
    LLM_FALLBACK_PROVIDER
    if LLM_FALLBACK_PROVIDER in MODELO_PADRAO
    and LLM_FALLBACK_PROVIDER != PROVEDOR
    and _CHAVE.get(LLM_FALLBACK_PROVIDER)
    else None
)

# Teto de 2. Em 429 o cliente espera o retry-after antes de repetir, entao cada
# tentativa a mais multiplica a espera que o usuario sente.
TENTATIVAS = 2
TIMEOUT_S = 90

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


def _reserva(*args, **kwargs):
    """Mesmo cliente no provedor de reserva, ou None quando nao ha reserva."""

    if RESERVA is None:
        return None

    return _cliente(*args, provedor=RESERVA, **kwargs)


def _com_reserva(*args, **kwargs):
    """
    Cliente do provedor principal que, se falhar, refaz a chamada na reserva.

    So para chamadas diretas (invoke). Agente com ferramentas precisa do
    modelo puro: a reserva dele entra pelo middleware, em agents.py.
    """

    principal = _cliente(*args, **kwargs)
    reserva = _reserva(*args, **kwargs)

    if reserva is None:
        return principal

    return principal.with_fallbacks([reserva])


# Devolve uma palavra: nome de rota ou de skill.
escolha_llm = _com_reserva(0, RACIOCINIO_CURTO, TETO_ESCOLHA)

# Devolve veredito curto e estruturado: juiz e guardrails. Teto curto e uma
# tentativa: o veredito leva ~0,5s medido, e um juiz travado de 90s x 2
# tentativas deixava a pessoa esperando mais de meio minuto. Quando ele falha,
# o fluxo ja aprova por padrao, entao perder a chamada custa pouco.
JUIZ_TIMEOUT_S = 20
JUIZ_TENTATIVAS = 1

revisao_llm = _com_reserva(
    0, RACIOCINIO_CURTO, TETO_VEREDITO,
    timeout=JUIZ_TIMEOUT_S, tentativas=JUIZ_TENTATIVAS,
)

# Escreve texto para a pessoa ler, de tamanho variável: sem teto.
texto_llm = _com_reserva(0, RACIOCINIO_CURTO)

# Agentes: aqui o raciocínio é o trabalho. Temperatura alta porque receita e
# sugestão ganham com variedade.
specialist_llm = _cliente(0.7)
specialist_reserva = _reserva(0.7)

# Estoque e registro e consulta, nao criacao: nao ganha com variedade nem com
# raciocinio longo. Medido: com o raciocinio padrao o agente gastou 2048 tokens
# pensando e devolveu resposta vazia, e cada mensagem passava de 10 mil tokens,
# acima dos 8 mil por minuto do plano do Groq, o que gera 429 e 12 a 26s de
# espera. Raciocinio curto e teto cortam isso na origem.
TETO_ESTOQUE = 1200

estoque_llm = _cliente(0, RACIOCINIO_CURTO, TETO_ESTOQUE)
estoque_reserva = _reserva(0, RACIOCINIO_CURTO, TETO_ESTOQUE)

# Segunda opinião do juiz. Semente diferente de proposito: com a mesma semente
# e temperatura zero, repetir a chamada devolve o MESMO veredito, e segunda
# opinião nenhuma. O sorteio precisa ser independente para a divergencia
# aparecer — e e a divergencia que diz que a primeira reprovacao foi ruido.
revisao_segunda_llm = _com_reserva(
    0, RACIOCINIO_CURTO, TETO_VEREDITO, semente=20261010,
    timeout=JUIZ_TIMEOUT_S, tentativas=JUIZ_TENTATIVAS,
)

# Apelidos por papel. Apontam para a mesma instância enquanto a configuração
# for a mesma; separar um deles depois é trocar uma linha.
roteador_llm = escolha_llm
seletor_llm = escolha_llm

juiz_llm = revisao_llm
guardrail_llm = revisao_llm

orquestrador_llm = texto_llm
memoria_llm = texto_llm

groq_llm = specialist_llm

# Agente de FAQ: modelo puro, porque create_agent precisa ligar as ferramentas
# nele. A reserva entra pelo middleware.
fast_llm = _cliente(0, RACIOCINIO_CURTO)
fast_reserva = _reserva(0, RACIOCINIO_CURTO)
