import json
import re
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langsmith import trace, traceable

from app.controller.config import logging
from app.core.agents import AGENTES_DAS_SKILLS, faq_app
from app.core.llms import (
    juiz_llm,
    orquestrador_llm,
    revisao_segunda_llm,
    roteador_llm,
    seletor_llm,
)
from app.core.prompts.prompt_juiz import JUIZ_PROMPT_COMPLETO
from app.core.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO
from app.core.skills import catalogo, do_agente
from app.guardrails.guardrails import (
    PII,
    anonimizar,
    checar_entrada,
    checar_saida,
)
from app.observability.background import em_segundo_plano
from app.observability.cost import estimate_cost_usd, extrair_tokens
from app.observability.tool_logging_callback import ToolLoggingCallback
from app.observability.tracing import generate_trace_id, span
from app.repository.mongodb.conversations import ConversationsRepository
from app.repository.mongodb.metrics import MetricsRepository
from app.repository.mongodb.tool_metrics import ToolMetricsRepository
from app.repository.qdrant.preferences_repository import PreferencesRepository

from .state import State

logger = logging.getLogger(__name__)

# Uma devolucao, nao duas: cada uma re-executa o agente inteiro, com todas as
# ferramentas de novo. No agente de receitas isso custa ~50s por rodada, e a
# segunda tentativa quase nunca salva o que a primeira nao salvou.
LIMITE_DEVOLUCOES = 1
LIMITE_EVIDENCIA = 1500
LIMITE_EVIDENCIAS_TOTAL = 4000
TURNOS_PARA_O_JUIZ = 4
TURNOS_PARA_O_AGENTE = 10

# As rotas que o grafo sabe atender. Qualquer outra coisa vira fallback.
ROTAS = ("faq", "receitas", "estoque", "eventos", "saudacao", "fallback")

# "Oi" nao precisa de agente, juiz nem orquestrador: a resposta nao depende de
# dado nenhum. O roteador identifica e o fluxo devolve este texto direto, sem
# nenhuma chamada de LLM depois dele.
RESPOSTA_DE_SAUDACAO = (
    "Oi! Tudo bem? Posso te ajudar com o seu estoque, sugerir uma receita "
    "com o que você tem em casa ou organizar um evento. Por onde quer começar?"
)

# A mesma rota recebe "bom dia" e "obrigado, valeu". Responder cumprimento a
# quem agradeceu soa como quem nao leu, e distinguir aqui nao custa token.
RESPOSTA_DE_AGRADECIMENTO = (
    "Por nada! Se precisar de mais alguma coisa com o estoque, com receitas "
    "ou com um evento, é só chamar."
)

# "boa noite" fica de fora de proposito: serve de cumprimento e de despedida,
# e na duvida cumprimentar erra menos do que despedir.
_AGRADECIMENTO = re.compile(
    r"\b(obrigad[oa]|obg|valeu|vlw|agrade[çc]|tmj|falou|t[ôo]\s+indo|"
    r"at[ée]\s+(mais|logo|amanh[ãa])|tchau)\b",
    re.IGNORECASE,
)

# Abertura das respostas montadas sem o orquestrador, usada so quando a pessoa
# saudou primeiro.
SAUDACAO_CURTA = "Oi!"

# O aplicativo ja cumprimenta a pessoa, entao o chat nao cumprimenta por conta
# propria: so retribui. Decidido aqui, em Python, porque e deterministico e o
# orquestrador nao recebe a mensagem original.
_SAUDOU = re.compile(
    r"^\W*\b(oi+|ol[áa]|al[ôo]|opa|e\s*a[íi]|fala|bom\s+dia|boa\s+(tarde|noite)|"
    r"hey|hi|hello|tudo\s+(bem|bom)|como\s+vai)\b",
    re.IGNORECASE,
)


def _saudou(mensagem: str) -> bool:
    return bool(_SAUDOU.match(mensagem or ""))

# Quando o seletor nao decide, cai na skill que so le. Dar ferramenta de
# escrita a um palpite e pior do que responder de menos.
SKILL_PADRAO = {
    "receitas": "receita-do-estoque",
    "eventos": "evento-gerenciar",
    "estoque": "estoque-consultar",
}


def _mascarar(valor):
    """
    Devolve uma copia do valor com PII mascarada, para o que sai no trace.

    Nunca altera o objeto recebido: o State segue intacto para o grafo.
    """

    if isinstance(valor, str):
        for tipo, padrao in PII:
            valor = re.sub(padrao, f"[{tipo}_MASCARADO]", valor)

        return valor

    if isinstance(valor, dict):
        return {
            chave: _mascarar(item)
            for chave, item in valor.items()
            if chave != "mapa_pii"
        }

    if isinstance(valor, (list, tuple)):
        return [_mascarar(item) for item in valor]

    return valor


def _entrada_do_no(inputs: dict) -> dict:
    return {"state": _mascarar(inputs.get("state", {}))}


def _saida_do_no(outputs):
    return _mascarar(outputs)


_TRACE_NO = {
    "run_type": "chain",
    "process_inputs": _entrada_do_no,
    "process_outputs": _saida_do_no,
}


@traceable(name="guardrail_entrada", **_TRACE_NO)
def guardrail_entrada(state: State) -> State:
    with span(state["trace_id"], "guardrail_entrada"):
        texto_anonimizado, mapa = anonimizar(state["mensagem"])

        state["mensagem"] = texto_anonimizado
        state["mapa_pii"] = mapa

        resultado = checar_entrada(texto_anonimizado)

        if resultado["bloqueado"]:
            state["entrada_aprovada"] = False
            state["resposta_agente"] = resultado["mensagem"]
        else:
            state["entrada_aprovada"] = True

        logger.info(
            "guardrail_entrada avaliado",
            extra={
                "trace_id": state["trace_id"],
                "stage": "input",
                "mensagem_anonimizada": texto_anonimizado,
                "entrada_aprovada": state["entrada_aprovada"],
            },
        )

    return state



@traceable(name="roteador", **_TRACE_NO)
def roteador(state: State) -> State:
    with span(state["trace_id"], "roteador"):
        historico = state.get("historico", [])

        mensagem_usuario = (
            f"Histórico: {_ultimos_turnos(historico, TURNOS_PARA_O_JUIZ)}\n"
            f"Mensagem: \"{state['mensagem']}\""
        )

        resposta = roteador_llm.invoke([
            SystemMessage(content=ROTEADOR_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        state["rota"] = _normalizar_rota(resposta.content)

        input_tokens, output_tokens = extrair_tokens(resposta)
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "roteador decidiu rota",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem_usuario,
                "rota": state["rota"],
            },
        )

    return state



def _normalizar_rota(bruto: str) -> str:
    """
    Converte a saída do roteador numa rota que o grafo atende.

    O valor ia cru para o add_conditional_edges, então qualquer coisa fora
    da lista — "Rota: estoque", "estoque.", texto vazio — derrubava a
    requisição inteira com erro de grafo, e não com uma resposta ruim.
    """

    texto = (bruto or "").strip().lower()

    if texto in ROTAS:
        return texto

    for rota in ROTAS:
        if rota in texto:
            return rota

    logger.warning(
        "roteador devolveu rota desconhecida; caindo em fallback",
        extra={"stage": "roteador", "bruto": texto[:120]},
    )

    return "fallback"


def _ultimos_turnos(historico: list[dict], quantos: int) -> list[dict]:
    """
    Recorta o histórico antes de ele entrar num prompt.

    Sem teto, uma conversa longa cresce sem limite dentro de cada chamada:
    estoura o contexto do modelo e queima cota por mensagem.
    """

    if not historico:
        return []

    return historico[-quantos:]


def _invocar_agente(
    agent,
    mensagem: str,
    historico: list,
    trace_id: str,
    revisao: str = "",
) -> tuple[str, int, int, list[dict]]:
    """
    Invoca um agente e extrai sua resposta final, os tokens e o que as
    ferramentas devolveram.

    Quando o juiz devolveu a rodada anterior, o motivo entra na mensagem como
    REVISAO: é a unica diferenca entre a primeira tentativa e as seguintes.
    """

    if revisao:
        mensagem = f"{mensagem}\nREVISAO={revisao}"

    messages = []

    for msg in historico:
        if msg["role"] == "user":
            messages.append(
                HumanMessage(content=msg["content"])
            )
        elif msg["role"] == "assistant":
            messages.append(
                AIMessage(content=msg["content"])
            )

    messages.append(
        HumanMessage(content=mensagem)
    )

    resultado = agent.invoke(
        {"messages": messages},
        config={
            "callbacks": [ToolLoggingCallback()],
            "metadata": {"trace_id": trace_id},
        },
    )

    mensagens_saida = resultado.get("messages", [])

    input_tokens = 0
    output_tokens = 0
    evidencias = []

    for msg in mensagens_saida:
        tokens_in, tokens_out = extrair_tokens(msg)
        input_tokens += tokens_in
        output_tokens += tokens_out

        if getattr(msg, "type", "") == "tool":
            evidencias.append({
                "ferramenta": getattr(msg, "name", "") or "ferramenta",
                "conteudo": msg.content,
            })

    if mensagens_saida:
        return (
            mensagens_saida[-1].content,
            input_tokens,
            output_tokens,
            evidencias,
        )

    return "", input_tokens, output_tokens, evidencias



@traceable(name="agente_faq", **_TRACE_NO)
def agente_faq(state: State) -> State:
    with span(state["trace_id"], "faq"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        mensagem = (
            f"ROUTE=faq\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}"
        )

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            faq_app,
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        # FAQ nao tem juiz nem dado de dominio para compor: o envelope ja traz
        # a frase pronta. Montando aqui, a rota economiza a chamada inteira do
        # orquestrador. Se o envelope nao servir, fica vazio e ele assume.
        state["resposta_final"] = _montar_sem_modelo(
            resposta_agente,
            _saudou(state["mensagem"]),
        )

        logger.debug(
            "agente_faq respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state



def _preferencias_prontas(account_id: int, pergunta: str) -> str:
    """
    Le as preferencias aqui, antes de chamar o agente, e nao por ferramenta.

    A leitura nao depende de nada e e sempre necessaria para sugerir receita.
    Deixada como ferramenta, ela custava uma ida inteira ao modelo: o prompt do
    agente (~1.800 tokens) era reenviado so para ele decidir chamar, e com teto
    de 8.000 tokens por minuto essa ida sozinha empurrava o fim da fila para o
    429. A ferramenta continua disponivel para o agente refinar a busca.
    """

    try:
        preferencias = PreferencesRepository.buscar_preferencias(
            account_id=account_id,
            busca=pergunta,
            limite=5,
        )
    except Exception:
        logger.warning(
            "nao foi possivel pre-carregar preferencias, o agente pode "
            "consultar pela ferramenta",
            exc_info=True,
        )

        return ""

    if not preferencias:
        return "nenhuma preferência registrada"

    return "; ".join(str(item) for item in preferencias)


@traceable(name="agente_receitas", **_TRACE_NO)
def agente_receitas(state: State) -> State:
    with span(state["trace_id"], "receitas"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        household_id = state.get(
            "household_account_id",
            0,
        )

        account_id = state.get(
            "account_id",
            0,
        )

        preferencias = _preferencias_prontas(account_id, state["mensagem"])

        mensagem = (
            f"ROUTE=receitas\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"PROFILE_ID={household_id}\n"
            f"ACCOUNT_ID={account_id}"
        )

        if preferencias:
            mensagem += f"\nPREFERENCIAS={preferencias}"

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            AGENTES_DAS_SKILLS[_escolher_skill("receitas", state)],
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente

        # O juiz precisa ver as preferencias como lastro: vindas pela entrada,
        # elas nao passam pelo callback que registra retorno de ferramenta.
        if preferencias:
            evidencias = [
                {"ferramenta": "consultar_preferencias", "conteudo": preferencias}
            ] + evidencias

        state["evidencias"] = state.get("evidencias", []) + evidencias
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_receitas respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




@traceable(name="agente_estoque", **_TRACE_NO)
def agente_estoque(state: State) -> State:
    with span(state["trace_id"], "estoque"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        household_id = state.get(
            "household_account_id",
            0,
        )

        mensagem = (
            f"ROUTE=stock\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"PROFILE_ID={household_id}"
        )

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            AGENTES_DAS_SKILLS[_escolher_skill("estoque", state)],
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_estoque respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




@traceable(name="agente_eventos", **_TRACE_NO)
def agente_eventos(state: State) -> State:
    with span(state["trace_id"], "eventos"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        household_id = state.get(
            "household_account_id",
            0,
        )

        account_id = state.get(
            "account_id",
            0,
        )

        mensagem = (
            f"ROUTE=events\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"HOUSEHOLD_ID={household_id}\n"
            f"PROFILE_ID={household_id}\n"
            f"ACCOUNT_ID={account_id}"
        )

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_agente(
            AGENTES_DAS_SKILLS[_escolher_skill("eventos", state)],
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        state["resposta_agente"] = resposta_agente
        state["evidencias"] = state.get("evidencias", []) + evidencias
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "agente_eventos respondeu",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem,
                "resposta_agente": state["resposta_agente"],
            },
        )

    return state




def _compactar(conteudo: str) -> tuple[str, str]:
    """
    Reduz o retorno da ferramenta ao que o juiz precisa para conferir lastro.

    Lista de registros vira uma linha por item, sem os campos de id: eles sao
    um terco do payload e nao dizem nada sobre lastro. Corta em item inteiro,
    nunca no meio de um, e devolve o aviso do que ficou de fora.
    """

    try:
        dados = json.loads(conteudo)
    except (ValueError, TypeError):
        dados = None

    if not isinstance(dados, list) or not dados:
        if len(conteudo) > LIMITE_EVIDENCIA:
            return conteudo[:LIMITE_EVIDENCIA], " (cortado por tamanho)"

        return conteudo, ""

    if not all(isinstance(registro, dict) for registro in dados):
        if len(conteudo) > LIMITE_EVIDENCIA:
            return conteudo[:LIMITE_EVIDENCIA], " (cortado por tamanho)"

        return conteudo, ""

    itens = [
        " ".join(
            f"{chave}={valor}"
            for chave, valor in registro.items()
            if not chave.endswith("_id") and valor not in ("", None)
        )
        for registro in dados
    ]

    mantidos = []
    total = 0

    for item in itens:
        if total + len(item) > LIMITE_EVIDENCIA:
            break

        total += len(item) + 2
        mantidos.append(item)

    omitidos = len(itens) - len(mantidos)
    aviso = f" (+{omitidos} de {len(itens)} itens omitidos por tamanho)" if omitidos else ""

    return "; ".join(mantidos), aviso


def _formatar_evidencias(evidencias: list[dict]) -> str:
    """
    Monta o bloco de evidencias do juiz com o que as ferramentas devolveram.

    O teto existe para o juiz nao virar gargalo de latencia, mas corte
    silencioso custa muito mais caro do que economiza: o juiz nao distingue
    "nao existe" de "nao me mostraram", reprova lastro legitimo e paga uma
    rodada inteira do agente. Por isso compacta antes de cortar, corta em item
    inteiro e sempre declara o que ficou de fora.
    """

    if not evidencias:
        return "nenhuma"

    linhas = []
    total = 0

    for evidencia in evidencias:
        ferramenta = evidencia.get("ferramenta", "ferramenta")
        conteudo, aviso = _compactar(str(evidencia.get("conteudo", "")))

        linha = f"- {ferramenta}: {conteudo}{aviso}"

        if total + len(linha) > LIMITE_EVIDENCIAS_TOTAL:
            linhas.append("- (demais retornos omitidos por tamanho)")
            break

        total += len(linha)
        linhas.append(linha)

    return "\n".join(linhas)


def _formatar_conversa(historico: list[dict]) -> str:
    """
    Ultimos turnos, para o juiz poder ver repeticao e insistencia.

    Sem isto a regra de nao repetir pergunta ja respondida e inverificavel:
    o juiz recebia so a mensagem da vez.
    """

    if not historico:
        return "primeira mensagem da conversa"

    linhas = []

    for turno in historico[-TURNOS_PARA_O_JUIZ:]:
        quem = "usuário" if turno.get("role") == "user" else "Ceris"
        conteudo = str(turno.get("content", ""))[:LIMITE_EVIDENCIA]
        linhas.append(f"- {quem}: {conteudo}")

    return "\n".join(linhas)


def _ler_veredito(texto: str) -> tuple[str, str]:
    """
    Le as duas linhas do juiz.

    Falha para APROVADO de proposito: juiz que nao respondeu no formato, ou
    que devolveu sem dizer o motivo, nao e razao para travar a resposta do
    usuario.
    """

    veredito = "APROVADO"
    motivo = ""

    for linha in texto.splitlines():
        limpa = linha.strip()

        if limpa.upper().startswith("VEREDITO:"):
            if "DEVOLVER" in limpa.split(":", 1)[1].upper():
                veredito = "DEVOLVER"
        elif limpa.upper().startswith("MOTIVO:"):
            motivo = limpa.split(":", 1)[1].strip()

    if veredito == "DEVOLVER" and not motivo:
        return "APROVADO", ""

    return veredito, motivo


# Campos que sao escolha de oficio do agente e NAO tem como ser conferidos
# contra o estoque, que conta unidades e nao pesos. Deixados a vista, o juiz
# reprova toda receita por "200 ml sem lastro" e cada reprovacao re-executa o
# agente inteiro. Os nomes dos ingredientes continuam a vista: esses sim se
# conferem contra a evidencia, e e ali que mora a alucinacao que importa.
SEM_COMO_CONFERIR = (
    "quantidade_total",
    "tem_suficiente",
    "porcoes",
    "tempo_estimado",
    "dificuldade",
)


def _podar(valor):
    if isinstance(valor, dict):
        return {
            chave: _podar(sub)
            for chave, sub in valor.items()
            if chave not in SEM_COMO_CONFERIR
        }

    if isinstance(valor, list):
        return [_podar(item) for item in valor]

    return valor


def _para_o_juiz(resposta_agente: str) -> str:
    """Tira do envelope o que o juiz nao tem evidencia para julgar."""

    try:
        dados = json.loads(resposta_agente)
    except (ValueError, TypeError):
        return resposta_agente

    if not isinstance(dados, dict):
        return resposta_agente

    return json.dumps(_podar(dados), ensure_ascii=False)


@traceable(name="juiz", **_TRACE_NO)
def juiz(state: State) -> State:
    with span(state["trace_id"], "juiz"):
        evidencias = _formatar_evidencias(state.get("evidencias", []))

        mensagem_usuario = (
            f"Rota: {state.get('rota', '')}\n"
            f"Conversa até agora:\n"
            f"{_formatar_conversa(state.get('historico', []))}\n"
            f"Pergunta: {state['mensagem']}\n"
            f"Evidências:\n"
            f"{evidencias}\n"
            f"Resposta do agente:\n"
            f"{_para_o_juiz(state.get('resposta_agente', ''))}"
        )

        resposta = juiz_llm.invoke([
            SystemMessage(content=JUIZ_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        veredito, motivo = _ler_veredito(resposta.content)

        input_tokens, output_tokens = extrair_tokens(resposta)

        # Devolver custa a re-execucao completa do agente: 43,0s em estoque e
        # 41,7s em receitas, medidos. Uma leitura do juiz custa ~0,5s. Como o
        # veredito varia entre execucoes — duas das tres devolucoes observadas
        # estavam erradas —, vale ler de novo antes de pagar a rodada.
        #
        # Semente diferente e obrigatorio: com a mesma semente e temperatura
        # zero, repetir a chamada devolve o MESMO veredito e nao ha segunda
        # opiniao nenhuma.
        segunda = None

        if veredito == "DEVOLVER":
            segunda = revisao_segunda_llm.invoke([
                SystemMessage(content=JUIZ_PROMPT_COMPLETO),
                HumanMessage(content=mensagem_usuario),
            ])

            veredito_2, motivo_2 = _ler_veredito(segunda.content)

            entrada_2, saida_2 = extrair_tokens(segunda)
            input_tokens += entrada_2
            output_tokens += saida_2

            # Divergencia absolve: a reprovacao era ruido do sorteio.
            if veredito_2 == "APROVADO":
                veredito, motivo = "APROVADO", ""
            else:
                motivo = motivo_2 or motivo

        devolucoes = state.get("devolucoes", 0)

        if veredito == "DEVOLVER" and devolucoes < LIMITE_DEVOLUCOES:
            state["devolucoes"] = devolucoes + 1
            state["veredito_juiz"] = motivo
            state["limite_devolucoes"] = False
        else:
            state["veredito_juiz"] = ""
            state["limite_devolucoes"] = veredito == "DEVOLVER"

        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.info(
            "juiz avaliou a resposta do agente",
            extra={
                "trace_id": state["trace_id"],
                "stage": "juiz",
                "rota": state.get("rota", ""),
                "veredito": veredito,
                "motivo": motivo,
                "segunda_leitura": segunda is not None,
                "devolucoes": state.get("devolucoes", 0),
                "limite_devolucoes": state.get("limite_devolucoes", False),
            },
        )

    return state



PROMPT_SELETOR = """\
Escolha qual capacidade atende o pedido abaixo.

Capacidades:
{catalogo}

Conversa até agora:
{conversa}

Pedido: {pedido}

Responda APENAS com o nome da capacidade, nada mais.
"""


def _escolher_skill(agente: str, state: State) -> str:
    """
    O proprio agente escolhe a sua skill, entre as 3 a 5 do dominio dele.

    Fica aqui, e nao no roteador, por dois motivos: o roteador escolheria entre
    13 opcoes em vez de 5, e a escolha costuma depender do que o dominio sabe.
    O catalogo custa ~160 tokens e poupa ~1800 no prompt do agente.

    Nome irreconhecivel cai na skill padrao, que e a de leitura.
    """

    skills = do_agente(agente)
    padrao = SKILL_PADRAO.get(agente, skills[0].nome if skills else "")

    if len(skills) < 2:
        return padrao

    pedido = PROMPT_SELETOR.format(
        catalogo=catalogo(agente),
        conversa=_formatar_conversa(state.get("historico", [])),
        pedido=state["mensagem"],
    )

    try:
        resposta = seletor_llm.invoke([HumanMessage(content=pedido)])
    except Exception:
        logger.exception(
            "seletor de skill falhou; usando a padrao",
            extra={"trace_id": state.get("trace_id", ""), "stage": "seletor"},
        )
        return padrao

    bruto = (resposta.content or "").strip().lower()
    nomes = [x.nome for x in skills]

    escolhida = next((n for n in nomes if n == bruto), None)
    if escolhida is None:
        escolhida = next((n for n in nomes if n in bruto), padrao)

    input_tokens, output_tokens = extrair_tokens(resposta)
    state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
    state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

    logger.info(
        "skill escolhida",
        extra={
            "trace_id": state.get("trace_id", ""),
            "stage": "seletor",
            "agente": agente,
            "skill": escolhida,
            "bruto": bruto[:60],
        },
    )

    return escolhida


@traceable(name="saudacao", **_TRACE_NO)
def saudacao(state: State) -> State:
    """Responde "Oi" sem nenhuma chamada de LLM: nada aqui depende de dado."""

    with span(state["trace_id"], "saudacao"):
        if _AGRADECIMENTO.search(state.get("mensagem", "")):
            state["resposta_final"] = RESPOSTA_DE_AGRADECIMENTO
        else:
            state["resposta_final"] = RESPOSTA_DE_SAUDACAO

        logger.debug(
            "saudacao respondida sem modelo",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "resposta_final": state["resposta_final"],
            },
        )

    return state


def _montar_sem_modelo(resposta_agente: str, saudou: bool = False) -> str:
    """
    Monta o texto final a partir do envelope, sem chamar o orquestrador.

    Serve para a rota de FAQ, que nao tem juiz nem dado de dominio para
    compor: o envelope ja traz a frase pronta e o orquestrador so a repetia,
    cobrando uma chamada inteira por isso. Devolve string vazia quando o
    envelope nao da para aproveitar — ai o orquestrador assume, como antes.
    """

    try:
        dados = json.loads(resposta_agente)
    except (ValueError, TypeError):
        return ""

    if not isinstance(dados, dict):
        return ""

    abertura = f"{SAUDACAO_CURTA} " if saudou else ""

    esclarecer = str(dados.get("esclarecer") or "").strip()

    # Pergunta de clarificacao encerra a mensagem e anda sozinha.
    if esclarecer:
        return f"{abertura}{esclarecer}"

    partes = [str(dados.get("resposta") or "").strip()]

    if not partes[0]:
        return ""

    for campo in ("recomendacao", "acompanhamento"):
        texto = str(dados.get(campo) or "").strip()

        # Sem modelo nao da para reescrever, so da para nao repetir: entra o
        # que ainda nao foi dito.
        if texto and texto.lower() not in " ".join(partes).lower():
            partes.append(texto)

    return abertura + " ".join(partes)


@traceable(name="orquestrador", **_TRACE_NO)
def orquestrador(state: State) -> State:
    with span(state["trace_id"], "orquestrador"):
        resposta_agente = state.get(
            "resposta_agente",
            "",
        )

        rota = state.get(
            "rota",
            "fallback",
        )

        mensagem_usuario = (
            f"Rota: {rota}\n"
            f"Resposta do agente: \"{resposta_agente}\""
        )

        if state.get("limite_devolucoes"):
            mensagem_usuario += "\nRevisão: não confirmada"

        if _saudou(state.get("mensagem", "")):
            mensagem_usuario += "\nSaudou: sim"

        resposta = orquestrador_llm.invoke([
            SystemMessage(content=ORQUESTRADOR_PROMPT_COMPLETO),
            HumanMessage(content=mensagem_usuario),
        ])

        state["resposta_final"] = resposta.content.strip()

        input_tokens, output_tokens = extrair_tokens(resposta)
        state["input_tokens"] = state.get("input_tokens", 0) + input_tokens
        state["output_tokens"] = state.get("output_tokens", 0) + output_tokens

        logger.debug(
            "orquestrador finalizou resposta",
            extra={
                "trace_id": state["trace_id"],
                "stage": "qa_debug",
                "mensagem_enviada": mensagem_usuario,
                "resposta_final": state["resposta_final"],
            },
        )

    return state



@traceable(name="guardrail_saida", **_TRACE_NO)
def guardrail_saida(state: State) -> State:
    with span(state["trace_id"], "guardrail_saida"):
        mapa = state.get(
            "mapa_pii",
            {},
        )

        resultado = checar_saida(
            state["resposta_final"],
            mapa,
        )

        # Bloqueio entrega a mensagem segura e encerra. Nao volta ao
        # orquestrador: ele so tem o envelope que gerou o risco e produziria o
        # mesmo texto, gastando uma chamada para repetir o problema.
        if resultado.get("bloqueado"):
            state["resposta_final"] = resultado["mensagem"]

            logger.warning(
                "guardrail de saida bloqueou a resposta",
                extra={
                    "trace_id": state["trace_id"],
                    "stage": "output",
                    "motivo": resultado.get("motivo", ""),
                },
            )
        else:
            state["resposta_final"] = resultado["conteudo"]

        state["saida_aprovada"] = True

    return state



def decidir_pos_guardrail_entrada(state: State) -> str:
    if not state["entrada_aprovada"]:
        return "orquestrador"

    return "roteador"


def decidir_rota(state: State) -> str:
    return state["rota"]


def decidir_pos_faq(state: State) -> str:
    """Montou o texto sem modelo, vai direto para a revisao de saida."""

    if state.get("resposta_final"):
        return "guardrail_saida"

    return "orquestrador"


def decidir_pos_juiz(state: State) -> str:
    if state.get("veredito_juiz"):
        rota = state.get("rota", "")

        if rota in ("receitas", "estoque", "eventos"):
            return rota

        return "orquestrador"

    return "orquestrador"


def decidir_pos_guardrail_saida(state: State) -> str:
    if not state["saida_aprovada"]:
        return "orquestrador"

    return END



def _registrar_metrica(
    trace_id: str,
    route: str,
    started_at,
    finished_at,
    duration_ms: float,
    erro: bool,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Conta as tools e grava a metrica da requisicao, fora do caminho critico."""

    MetricsRepository.save_request_metric(
        trace_id=trace_id,
        route=route,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        tool_calls=ToolMetricsRepository.count_by_trace_id(trace_id),
        error=erro,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(input_tokens, output_tokens),
    )


def executar_chat(
    mensagem: str,
    session_id: str | None,
    household_account_id: int,
    account_id: int,
) -> dict:
    """
    Função pública que encapsula a execução do workflow.
    """

    trace_id = generate_trace_id()

    if session_id and ConversationsRepository.sessao_ativa(session_id):
        historico = ConversationsRepository.get_historico(
            session_id
        )
    else:
        session_id = ConversationsRepository.create_session(
            account_id
        )

        historico = []

    started_at = datetime.now(UTC)
    resultado = None
    erro = False

    try:
        with trace(
            name="ceris_chat_request",
            run_type="chain",
            metadata={
                "session_id": session_id,
                "household_account_id": household_account_id,
                "account_id": account_id,
                "trace_id": trace_id,
            },
        ):
            resultado = ceris_workflow.invoke({
                "mensagem": mensagem,
                "historico": historico,
                "rota": "fallback",
                "resposta_agente": "",
                "resposta_final": "",
                "entrada_aprovada": False,
                "saida_aprovada": False,
                "mapa_pii": {},
                "evidencias": [],
                "veredito_juiz": "",
                "devolucoes": 0,
                "limite_devolucoes": False,
                "household_account_id": household_account_id,
                "account_id": account_id,
                "trace_id": trace_id,
                "input_tokens": 0,
                "output_tokens": 0,
            })
    except Exception:
        erro = True

        logger.exception(
            "Falha ao executar workflow",
            extra={"trace_id": trace_id, "stage": "workflow"},
        )

        raise
    finally:
        finished_at = datetime.now(UTC)
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        if resultado is not None and not resultado.get("entrada_aprovada", True):
            erro = True

        input_tokens = resultado.get("input_tokens", 0) if resultado is not None else 0
        output_tokens = resultado.get("output_tokens", 0) if resultado is not None else 0

        # A contagem de tools vai junto da gravacao, na mesma tarefa: ela le o
        # que o callback das tools escreveu, e a fila de uma thread garante que
        # aquelas escritas ja passaram. Separadas, a contagem poderia correr
        # antes e registrar zero.
        em_segundo_plano(
            _registrar_metrica,
            trace_id=trace_id,
            route=resultado.get("rota", "fallback") if resultado is not None else "fallback",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            erro=erro,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    resposta = resultado["resposta_final"]

    ConversationsRepository.append_messages(
        session_id,
        mensagem,
        resposta,
    )

    return {
        "resposta": resposta,
        "session_id": session_id,
    }


graph = StateGraph(State)

graph.add_node(
    "guardrail_entrada",
    guardrail_entrada,
)

graph.add_node(
    "roteador",
    roteador,
)

graph.add_node(
    "faq",
    agente_faq,
)

graph.add_node(
    "receitas",
    agente_receitas,
)

graph.add_node(
    "estoque",
    agente_estoque,
)

graph.add_node(
    "eventos",
    agente_eventos,
)

graph.add_node(
    "juiz",
    juiz,
)

graph.add_node(
    "saudacao",
    saudacao,
)

graph.add_node(
    "orquestrador",
    orquestrador,
)

graph.add_node(
    "guardrail_saida",
    guardrail_saida,
)



graph.set_entry_point(
    "guardrail_entrada"
)




graph.add_conditional_edges(
    "guardrail_entrada",
    decidir_pos_guardrail_entrada,
    {
        "roteador": "roteador",
        "orquestrador": "orquestrador",
    },
)



graph.add_conditional_edges(
    "roteador",
    decidir_rota,
    {
        "faq": "faq",
        "receitas": "receitas",
        "estoque": "estoque",
        "eventos": "eventos",
        "saudacao": "saudacao",
        "fallback": "orquestrador",
    },
)



graph.add_conditional_edges(
    "faq",
    decidir_pos_faq,
    {
        "guardrail_saida": "guardrail_saida",
        "orquestrador": "orquestrador",
    },
)

# Saudacao nao passa por orquestrador nem por guardrail: o texto e constante,
# nosso, e nao carrega dado de ninguem para revisar ou mascarar.
graph.add_edge(
    "saudacao",
    END,
)

graph.add_edge(
    "receitas",
    "juiz",
)

graph.add_edge(
    "estoque",
    "juiz",
)

graph.add_edge(
    "eventos",
    "juiz",
)




graph.add_conditional_edges(
    "juiz",
    decidir_pos_juiz,
    {
        "receitas": "receitas",
        "estoque": "estoque",
        "eventos": "eventos",
        "orquestrador": "orquestrador",
    },
)



graph.add_edge(
    "orquestrador",
    "guardrail_saida",
)



graph.add_conditional_edges(
    "guardrail_saida",
    decidir_pos_guardrail_saida,
    {
        "orquestrador": "orquestrador",
        END: END,
    },
)


ceris_workflow = graph.compile()