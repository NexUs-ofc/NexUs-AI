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

from langchain_groq import ChatGroq

from ..config import GROQ_API_KEY

MODELO = "openai/gpt-oss-20b"

# Teto de 2. Em 429 o cliente espera o retry-after antes de repetir, entao cada
# tentativa a mais multiplica a espera que o usuario sente.
TENTATIVAS = 2
TIMEOUT_S = 90

# Única escolha que reduz: "medium" devolve o mesmo que o padrão.
RACIOCINIO_CURTO = "low"

# Fixa a amostragem para que duas execuções iguais deem o mesmo resultado. Sem
# isso, comparar antes e depois de uma mudança vira leitura de ruído.
SEMENTE = 42

TETO_ESCOLHA = 300
TETO_VEREDITO = 600


def _cliente(
    temperatura: float,
    raciocinio: str | None = None,
    teto: int | None = None,
    semente: int | None = SEMENTE,
    timeout: int = TIMEOUT_S,
    tentativas: int = TENTATIVAS,
):
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
        model=MODELO,
        temperature=temperatura,
        api_key=GROQ_API_KEY,
        max_retries=tentativas,
        request_timeout=timeout,
        **extras,
    )


# Devolve uma palavra: nome de rota ou de skill.
escolha_llm = _cliente(0, RACIOCINIO_CURTO, TETO_ESCOLHA)

# Devolve veredito curto e estruturado: juiz e guardrails. Teto curto e uma
# tentativa: o veredito leva ~0,5s medido, e um juiz travado de 90s x 2
# tentativas deixava a pessoa esperando mais de meio minuto. Quando ele falha,
# o fluxo ja aprova por padrao, entao perder a chamada custa pouco.
JUIZ_TIMEOUT_S = 20
JUIZ_TENTATIVAS = 1

revisao_llm = _cliente(
    0, RACIOCINIO_CURTO, TETO_VEREDITO,
    timeout=JUIZ_TIMEOUT_S, tentativas=JUIZ_TENTATIVAS,
)

# Escreve texto para a pessoa ler, de tamanho variável: sem teto.
texto_llm = _cliente(0, RACIOCINIO_CURTO)

# Agentes: aqui o raciocínio é o trabalho. Temperatura alta porque receita e
# sugestão ganham com variedade.
specialist_llm = _cliente(0.7)

# Estoque e registro e consulta, nao criacao: nao ganha com variedade nem com
# raciocinio longo. Medido: com o raciocinio padrao o agente gastou 2048 tokens
# pensando e devolveu resposta vazia, e cada mensagem passava de 10 mil tokens,
# acima dos 8 mil por minuto do plano do Groq, o que gera 429 e 12 a 26s de
# espera. Raciocinio curto e teto cortam isso na origem.
TETO_ESTOQUE = 1200

estoque_llm = _cliente(0, RACIOCINIO_CURTO, TETO_ESTOQUE)

# Segunda opinião do juiz. Semente diferente de proposito: com a mesma semente
# e temperatura zero, repetir a chamada devolve o MESMO veredito, e segunda
# opinião nenhuma. O sorteio precisa ser independente para a divergencia
# aparecer — e e a divergencia que diz que a primeira reprovacao foi ruido.
revisao_segunda_llm = _cliente(
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
fast_llm = texto_llm
