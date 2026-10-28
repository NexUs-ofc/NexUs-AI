import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langsmith import trace, traceable

from app.auth import identidade
from app.config import JUDGE_PROVIDER
from app.controller.config import logging
from app.core.agents import AGENTES_DAS_SKILLS, faq_app
from app.core.contexto_conversa import (
    assunto_do_turno,
    pedido_lista_generico,
    resolver_assunto,
)
from app.core.judge import Verdict, deterministic_verdict, evaluate_jev, privacy_verdict
from app.core.llms import (
    MODELO,
    juiz_llm,
    orquestrador_llm,
    roteador_llm,
    seletor_llm,
    texto,
)
from app.core.prompts.prompt_juiz import JUIZ_PROMPT_COMPLETO
from app.core.prompts.prompt_orquestrador import ORQUESTRADOR_PROMPT_COMPLETO
from app.core.prompts.prompt_roteador import ROTEADOR_PROMPT_COMPLETO
from app.core.provider_policy import transient
from app.core.runtime_budget import BudgetExceeded, request_budget
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
from app.repository.pgsql.config import SessionLocal
from app.repository.pgsql.profile import ProfileRepository
from app.repository.qdrant.preferences_repository import PreferencesRepository
from app.validation import ingredientes_basicos_ausentes

from .state import State

logger = logging.getLogger(__name__)
_PROFILE_READS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ceris-profile")

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


# O chat nao adiciona produto ao estoque. Deixado para o modelo, o aviso as
# vezes nao saia; aqui e fixo e sem chamada nenhuma.
RESPOSTA_DE_CADASTRO = (
    "Por aqui eu não adiciono produtos ao estoque: o cadastro é feito pelo "
    "aplicativo. Se quiser, posso ver o que você já tem ou tirar algo que acabou."
)

_CADASTRO = re.compile(
    r"\b(cadastr\w*|adicion\w*|acrescent\w*|coloc[ae]\w*|bot[ae]\w*|comprei)\b",
    re.IGNORECASE,
)

# "comprei arroz e acabou o leite" tem saida: vai para o agente.
_SAIDA_DO_ESTOQUE = re.compile(
    r"\b(acab\w*|consum\w*|comi|usei|gastei|joguei|jogar|descart\w*|tir[ae]\w*|"
    r"remov\w*|venc\w*|estragou)\b",
    re.IGNORECASE,
)


def _pede_cadastro(mensagem: str) -> bool:
    """Pedido de adicionar ao estoque, sem pergunta nem saida misturada."""

    mensagem = mensagem or ""

    return (
        "?" not in mensagem
        and bool(_CADASTRO.search(mensagem))
        and not _SAIDA_DO_ESTOQUE.search(mensagem)
    )

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

        state["rota"] = _normalizar_rota(texto(resposta))

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


def _ultima_receita(historico: list[dict]) -> dict | None:
    """Preserva o objeto apresentado mesmo depois de trocar de seção."""
    for turno in reversed(historico or []):
        recipe = turno.get("receita") if turno.get("role") == "assistant" else None
        if isinstance(recipe, dict) and _formatar_receita(recipe):
            return deepcopy(recipe)
    return None


def _contexto_receita(state: State) -> str:
    assunto = resolver_assunto(state.get("historico", []), state.get("mensagem", ""))
    if not assunto:
        return ""
    if assunto["tipo"] == "receita":
        return "\nULTIMA_RECEITA_APRESENTADA=" + json.dumps(assunto["receita"], ensure_ascii=False, default=str)
    return ("\nASSUNTO_ATIVO=" + json.dumps(assunto, ensure_ascii=False, default=str) +
            "\nUma lista genérica refere-se a este evento, não a uma receita avulsa antiga. "
            "Consulte o evento e seu cardápio. Se faltar confirmação dos pratos ou quantidades, "
            "peça esclarecimento; não use outra receita como substituição.")


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

    # A correção usa os recibos existentes. Não deixa uma crítica do juiz
    # produzir uma segunda criação/cancelamento com argumentos diferentes.
    from contextlib import nullcontext

    from langgraph.errors import GraphRecursionError

    try:
        with identidade.reparo_de_resposta() if revisao else nullcontext():
            resultado = agent.invoke(
                {"messages": messages},
                config={"callbacks": [ToolLoggingCallback()], "metadata": {"trace_id": trace_id},
                        "recursion_limit": 16},
            )
    except GraphRecursionError:
        logger.exception(
            "GraphRecursionError dentro do agente",
            extra={
                "trace_id": trace_id,
                "stage": "agent",
                "recursion_limit": 16,
            },
        )
        return json.dumps({"resposta": "Não consegui concluir todas as etapas. Confira os registros atuais antes de repetir uma alteração."}), 0, 0, []

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
            texto(mensagens_saida[-1]),
            input_tokens,
            output_tokens,
            evidencias,
        )

    return "", input_tokens, output_tokens, evidencias



def _lista_gravada(response: str, evidences: list[dict]) -> tuple[dict, str] | None:
    envelope = _ler_envelope(response)
    if not envelope or not isinstance(envelope.get("lista"), dict):
        return None
    key = envelope["lista"].get("_id")
    for evidence in reversed(evidences):
        name = evidence.get("ferramenta")
        if name not in {"create_list", "update_list", "alterar_item_lista", "renomear_lista"}:
            continue
        try:
            saved = json.loads(evidence.get("conteudo", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(saved, dict) and saved.get("_id") == key and isinstance(saved.get("array_list"), list):
            return saved, name
    return None


def _invocar_com_confirmacao(agent, mensagem, historico, trace_id, revisao=""):
    """Não confirma escrita sem evidência, mesmo que o modelo afirme sucesso."""
    response, tokens_in, tokens_out, evidences = _invocar_agente(
        agent, mensagem, historico, trace_id, revisao,
    )
    operations = {
        "Salvar receita": "salvar_receita",
        "Criar lista de compras": "create_list",
        "Atualizar lista de compras": "update_list",
    }
    for attempt in range(2):
        envelope = _ler_envelope(response)
        if not envelope:
            return response, tokens_in, tokens_out, evidences
        expected = operations.get(envelope.get("intencao"))
        if not expected or envelope.get("esclarecer"):
            return response, tokens_in, tokens_out, evidences
        confirmed = None
        for evidence in evidences:
            actual = evidence.get("ferramenta")
            if actual != expected and not (expected == "update_list" and actual in {"alterar_item_lista", "renomear_lista"}):
                continue
            try:
                result = json.loads(evidence.get("conteudo", ""))
            except (ValueError, TypeError):
                continue
            if not isinstance(result, dict):
                continue
            if expected == "salvar_receita":
                if result.get("status") == "sucesso" and result.get("receita", {}).get("_id"):
                    confirmed = result
            elif result.get("_id") and isinstance(result.get("array_list"), list):
                confirmed = result
        if confirmed is not None:
            if expected == "salvar_receita":
                envelope["receita"] = confirmed["receita"]
                response = json.dumps(envelope, ensure_ascii=False, default=str)
            if expected in {"create_list", "update_list"}:
                envelope["lista"] = confirmed
                response = json.dumps(envelope, ensure_ascii=False)
            return response, tokens_in, tokens_out, evidences
        if expected == "salvar_receita":
            validation_prefix = "FALHA: receita não salva. "
            invalid = next((str(e.get("conteudo", ""))[len(validation_prefix):]
                            for e in reversed(evidences)
                            if e.get("ferramenta") == "salvar_receita"
                            and str(e.get("conteudo", "")).startswith(validation_prefix)), None)
            if invalid:
                response = json.dumps({
                    "dominio": envelope.get("dominio", ""),
                    "intencao": "Salvar receita",
                    "resposta": f"Não salvei a receita. {invalid}",
                    "esclarecer": f"{invalid} Pode corrigir esses dados antes de salvar?",
                }, ensure_ascii=False)
                return response, tokens_in, tokens_out, evidences
        if attempt == 0 and identidade.reservar_reparo():
            tool = "renomear_lista ou alterar_item_lista" if expected == "update_list" else expected
            correction = (
                "A operação NÃO tem confirmação. Consulte os dados e execute "
                f"{tool} com os argumentos necessários. Não basta escrever "
                "que fez. Se não conseguir, informe a falha sem confirmar sucesso."
            )
            response, more_in, more_out, more_evidence = _invocar_agente(
                agent, mensagem, historico, trace_id, correction,
            )
            tokens_in += more_in
            tokens_out += more_out
            evidences += more_evidence
        else:
            response = json.dumps({
                "dominio": envelope.get("dominio", ""),
                "intencao": envelope.get("intencao", ""),
                "resposta": (
                    "Não consegui confirmar o salvamento. Confira se as quantidades são positivas "
                    "e têm unidade, e se os demais dados da receita estão completos."
                    if expected == "salvar_receita" else
                    "Não consegui confirmar essa alteração. Tente novamente."
                ),
                "recomendacao": "",
            }, ensure_ascii=False)
    return response, tokens_in, tokens_out, evidences


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


def _restricoes_prontas(profile_id: int) -> str:
    """
    Restricoes alimentares do perfil (coluna dietary_restrictions, Postgres).

    Preferencias (gostos) ficam no Qdrant; restricoes, so aqui. Campo nulo,
    vazio ou leitura que falhou: a pessoa e tratada como sem restricao.
    """

    try:
        with SessionLocal() as session:
            restricoes = ProfileRepository(session).get_restrictions(profile_id)
    except Exception:
        logger.warning("nao foi possivel ler as restricoes do perfil", exc_info=True)
        return "FALHA: não foi possível consultar as restrições do perfil."

    if not restricoes:
        return "nenhuma restrição registrada"

    return "; ".join(restricoes)


@traceable(name="agente_receitas", **_TRACE_NO)
def agente_receitas(state: State) -> State:
    with span(state["trace_id"], "receitas"):
        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        account_id = state.get(
            "account_id",
            0,
        )

        prefs = _PROFILE_READS.submit(_preferencias_prontas, account_id, state["mensagem"])
        restrictions = _PROFILE_READS.submit(_restricoes_prontas, state.get("household_account_id", 0))
        preferencias, restricoes = prefs.result(), restrictions.result()
        if restricoes.startswith("FALHA"):
            state["resposta_agente"] = json.dumps({"resposta": "Não consegui consultar suas restrições alimentares agora. Tente novamente antes de gerar uma receita."})
            state["resposta_final"] = _montar_sem_modelo(state["resposta_agente"])
            return state

        mensagem = (
            f"ROUTE=receitas\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
            f"RESTRICOES={restricoes}\n"
        )

        if preferencias:
            mensagem += f"\nPREFERENCIAS={preferencias}"
        mensagem += _contexto_receita(state)

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_com_confirmacao(
            AGENTES_DAS_SKILLS[_escolher_skill("receitas", state)],
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        resposta_agente = _alinhar_receita_consultada(resposta_agente, evidencias)
        resposta_agente = _alinhar_receita_estoque(resposta_agente, evidencias)
        state["resposta_agente"] = resposta_agente

        # Receita sai daqui ja formatada (ingredientes e modo de preparo), sem
        # juiz nem orquestrador: o juiz reprovava ingrediente que nao estava no
        # estoque e empurrava o agente a enfiar o que havia em casa no prato, e
        # o orquestrador resumia a receita em texto corrido. Envelope que nao
        # da para aproveitar fica vazio e o orquestrador assume.
        state["resposta_final"] = _montar_sem_modelo(
            resposta_agente,
            _saudou(state["mensagem"]),
        )

        # O juiz precisa ver as preferencias como lastro: vindas pela entrada,
        # elas nao passam pelo callback que registra retorno de ferramenta.
        if preferencias:
            evidencias = [
                {"ferramenta": "consultar_preferencias", "conteudo": preferencias}
            ] + evidencias

        evidencias = [
            {"ferramenta": "restricoes_do_perfil", "conteudo": restricoes}
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
        if _pede_cadastro(state["mensagem"]):
            abertura = f"{SAUDACAO_CURTA} " if _saudou(state["mensagem"]) else ""
            state["resposta_final"] = abertura + RESPOSTA_DE_CADASTRO

            return state

        historico = _ultimos_turnos(
            state.get("historico", []),
            TURNOS_PARA_O_AGENTE,
        )

        mensagem = (
            f"ROUTE=stock\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
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

        mensagem = (
            f"ROUTE=events\n"
            f"PERGUNTA_ORIGINAL={state['mensagem']}\n"
        )
        mensagem += _contexto_receita(state)

        resposta_agente, input_tokens, output_tokens, evidencias = _invocar_com_confirmacao(
            AGENTES_DAS_SKILLS[_escolher_skill("eventos", state)],
            mensagem,
            historico,
            state["trace_id"],
            state.get("veredito_juiz", ""),
        )
        resposta_agente = _alinhar_lista_consultada(resposta_agente, evidencias)
        confirmed = _lista_gravada(resposta_agente, evidencias)
        state["lista_confirmada"] = confirmed is not None
        if confirmed:
            saved, operation = confirmed
            safe = {
                "dominio": "events",
                "intencao": "Criar lista de compras" if operation == "create_list" else "Atualizar lista de compras",
                "resposta": "Criei sua lista de compras." if operation == "create_list" else "Atualizei sua lista de compras.",
                "recomendacao": "",
                "lista": saved,
            }
            if any(not c.get("comparacao_confirmada") and not c.get("dispensa_compra")
                   for c in saved.get("conferencia", [])):
                safe["recomendacao"] = "Confira as quantidades disponíveis antes de comprar os itens que não puderam ser comparados."
            for evidence in evidencias:
                if evidence.get("ferramenta") == "ingredientes_para_comprar":
                    try:
                        check = json.loads(evidence.get("conteudo", ""))
                        if any(not c.get("comparacao_confirmada") and not c.get("dispensa_compra")
                               for c in check.get("conferencia", [])):
                            safe["recomendacao"] = "Confira as quantidades disponíveis antes de comprar os itens que não puderam ser comparados."
                    except (ValueError, TypeError, AttributeError):
                        pass
            resposta_agente = json.dumps(safe, ensure_ascii=False)
            state["resposta_final"] = _montar_sem_modelo(resposta_agente)
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




def _sem_ids(valor):
    """A projeção semântica dos dois lados exclui metadados não exibidos."""
    if isinstance(valor, dict):
        return {k: _sem_ids(v) for k, v in valor.items()
                if not k.endswith("_id") and k not in {"id", "foodId", "id_receita"}}
    if isinstance(valor, list):
        return [_sem_ids(v) for v in valor]
    return valor


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
    if isinstance(dados, (dict, list)):
        dados = _sem_ids(dados)
        conteudo = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))

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

    return json.dumps(_podar(_sem_ids(dados)), ensure_ascii=False)


@traceable(name="juiz", **_TRACE_NO)
def juiz(state: State) -> State:
    with span(state["trace_id"], "juiz"):
        response = state.get("resposta_agente", "")
        envelope = _ler_envelope(response)
        candidate = _montar_sem_modelo(response) or _para_o_juiz(response)
        evidence = _formatar_evidencias(state.get("evidencias", []))
        history = _formatar_conversa(state.get("historico", []))
        verdict = privacy_verdict(candidate) or deterministic_verdict(envelope, state.get("evidencias", []))
        if verdict is None:
            if JUDGE_PROVIDER == "jev":
                verdict = evaluate_jev(state["mensagem"], candidate, evidence, history)
            else:
                verdict = Verdict("review", "Avaliação pelo modelo de reserva.", "llm")
        jev_input = verdict.input_tokens if verdict.source == "jev" else 0
        jev_output = verdict.output_tokens if verdict.source == "jev" else 0
        # Uma única escalada, sem a antiga segunda opinião. Falha não significa
        # aprovação: entrega abstinência honesta quando não é possível validar.
        if verdict.decision == "review":
            tokens_in, tokens_out = verdict.input_tokens, verdict.output_tokens
            try:
                result = juiz_llm.invoke([
                    SystemMessage(content=JUIZ_PROMPT_COMPLETO),
                    HumanMessage(content=f"Rota: {state.get('rota', '')}\nConversa: {history}\n"
                                 f"Pergunta: {state['mensagem']}\nEvidências: {evidence}\n"
                                 f"Resposta do agente: {candidate}"),
                ])
                content = texto(result)
                match = re.search(r"VEREDITO:\s*(APROVADO|DEVOLVER)", content)
                if not match:
                    raise ValueError("invalid_judge_verdict")
                label, reason = _ler_veredito(content)
                if label != match[1]:
                    raise ValueError("invalid_judge_reason")
                more_in, more_out = extrair_tokens(result)
                verdict = Verdict("approve" if label == "APROVADO" else "repair", reason,
                                  "llm_fallback", verdict.scores, tokens_in + more_in, tokens_out + more_out)
            except Exception:  # noqa: BLE001 -- qualquer falha do avaliador exige abstinência.
                verdict = Verdict("abstain", "Não foi possível validar a resposta.", "unavailable",
                                  verdict.scores, tokens_in, tokens_out)
        count = state.get("devolucoes", 0)
        repair = (verdict.decision == "repair" and count < LIMITE_DEVOLUCOES
                  and identidade.reservar_reparo())
        state["veredito_juiz"] = verdict.reason if repair else ""
        state["devolucoes"] = count + int(repair)
        state["limite_devolucoes"] = verdict.decision in {"repair", "abstain"} and not repair
        state["juiz_aprovado"] = verdict.decision == "approve"
        state["juiz_seguro"] = verdict.decision == "approve" and verdict.source == "jev"
        state["decisoes_juiz"] = [*state.get("decisoes_juiz", []),
                                  "aprovado" if verdict.decision == "approve" else
                                  "devolvido" if repair else "nao_confirmado"]
        state["input_tokens"] = state.get("input_tokens", 0) + verdict.input_tokens - jev_input
        state["output_tokens"] = state.get("output_tokens", 0) + verdict.output_tokens - jev_output
        usage = state.get("judge_usage", {})
        state["judge_usage"] = {"provider": "typesafe", "model": verdict.scores.get("modelo", ""),
                                "input_tokens": usage.get("input_tokens", 0) + jev_input,
                                "output_tokens": usage.get("output_tokens", 0) + jev_output}
        logger.info("juiz avaliou a resposta do agente", extra={
            "trace_id": state["trace_id"], "stage": "juiz", "rota": state.get("rota", ""),
            "veredito": verdict.decision, "motivo": verdict.reason,
            "judge_source": verdict.source, "judge_scores": verdict.scores,
            "devolucoes": state["devolucoes"], "limite_devolucoes": state["limite_devolucoes"],
        })
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

    bruto = texto(resposta).strip().lower()
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


def _ler_envelope(resposta_agente: str) -> dict | None:
    """JSON do agente, tolerando a cerca de markdown (```json) que o Gemini poe."""

    bruto = (resposta_agente or "").strip()

    if bruto.startswith("```"):
        bruto = re.sub(r"\A```[a-zA-Z]*\s*|\s*```\Z", "", bruto)

    try:
        dados = json.loads(bruto)
    except (ValueError, TypeError):
        # Texto antes ou depois do JSON ("Aqui esta a receita: {...}"): tenta
        # o objeto de dentro antes de desistir e cair no orquestrador.
        inicio, fim = bruto.find("{"), bruto.rfind("}")

        if inicio < 0 or fim <= inicio:
            return None

        try:
            dados = json.loads(bruto[inicio:fim + 1])
        except (ValueError, TypeError):
            return None

    return dados if isinstance(dados, dict) else None


def _formatar_receita(receita) -> str:
    """Aceita envelopes da IA e documentos salvos, sem perder ingredientes."""
    if not isinstance(receita, dict):
        return ""
    title = str(receita.get("titulo") or receita.get("title") or "").strip()
    ingredients = receita.get("ingredientes") or receita.get("ingredients") or []
    instructions = receita.get("instrucoes") or receita.get("instructions") or []
    if isinstance(instructions, str):
        instructions = instructions.splitlines()
    steps = [
        re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        for step in instructions if isinstance(step, str)
        for line in step.splitlines() if line.strip()
    ]
    if not title or not ingredients or not steps:
        return ""
    servings = receita.get("porcoes") or receita.get("serving_size")
    minutes = receita.get("tempo_preparo_minutos") or receita.get("preparation_time_minutes")
    difficulty = receita.get("dificuldade") or receita.get("difficulty") or ""
    difficulty = {"easy": "fácil", "medium": "média", "hard": "difícil"}.get(difficulty, difficulty)
    details = " · ".join(str(value) for value in (
        f"{servings} porções" if servings else "",
        f"{minutes} minutos" if minutes else receita.get("tempo_estimado") or receita.get("estimated_time"),
        difficulty,
    ) if value)
    lines = [title + (f" ({details})" if details else ""), "", "Ingredientes:"]
    for item in ingredients:
        if not isinstance(item, dict):
            return ""
        name = str(item.get("ingrediente") or item.get("nome") or item.get("name") or "").strip()
        quantity = str(item.get("quantidade_total") or item.get("quantidade") or item.get("required_quantity") or "").strip()
        if not name or not quantity:
            return ""
        suffix = ""
        if item.get("comparacao_confirmada") is False and not item.get("dispensa_compra"):
            suffix = " (quantidade no estoque a conferir)"
        elif item.get("tem_suficiente") is False:
            suffix = " (falta comprar)"
        lines.append(f"- {name}: {quantity}{suffix}")
    lines += ["", "Modo de preparo:"]
    lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
    missing = [str(x) for x in receita.get("ingredientes_faltantes") or [] if x]
    if missing:
        lines += ["", f"Para comprar: {', '.join(missing)}."]
    return "\n".join(lines)


def _alinhar_receita_estoque(response: str, evidencias: list[dict]) -> str:
    """O estado do estoque vem do cálculo, não de uma reinterpretação do modelo."""
    envelope = _ler_envelope(response)
    if not envelope or not isinstance(envelope.get("receita"), dict):
        return response
    checks = None
    for evidence in evidencias:
        if evidence.get("ferramenta") != "ingredientes_para_comprar":
            continue
        try:
            data = json.loads(evidence.get("conteudo", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("conferencia"), list):
            checks = data
    if checks is None:
        return response
    by_name = {c["nome"].casefold().strip(): c for c in checks["conferencia"]}
    recipe = envelope["receita"]
    for ingredient in recipe.get("ingredientes") or []:
        if not isinstance(ingredient, dict):
            continue
        name = str(ingredient.get("ingrediente") or ingredient.get("name") or "").casefold().strip()
        check = by_name.get(name)
        if check:
            ingredient["tem_suficiente"] = check["tem_suficiente"] if check["comparacao_confirmada"] else None
            ingredient["comparacao_confirmada"] = check["comparacao_confirmada"]
            ingredient["dispensa_compra"] = check.get("dispensa_compra", False)
    recipe["ingredientes_faltantes"] = [i["name"] for i in checks["itens_para_comprar"]]
    return json.dumps(envelope, ensure_ascii=False)


def _alinhar_receita_consultada(response: str, evidencias: list[dict]) -> str:
    """Consulta reproduz o documento confirmado, sem reescrever o preparo."""
    envelope = _ler_envelope(response)
    if not envelope or envelope.get("intencao") != "Buscar receita anterior":
        return response
    for evidence in reversed(evidencias):
        if evidence.get("ferramenta") != "buscar_receitas_usuario":
            continue
        try:
            recipes = json.loads(evidence.get("conteudo", ""))
        except (ValueError, TypeError):
            return response
        if not isinstance(recipes, list) or len(recipes) != 1 or not isinstance(recipes[0], dict):
            return response
        envelope = {"dominio": "receitas", "intencao": "Buscar receita anterior",
                    "resposta": "Encontrei esta receita salva.", "receita": recipes[0]}
        return json.dumps(envelope, ensure_ascii=False)
    return response


def _alinhar_lista_consultada(response: str, evidencias: list[dict]) -> str:
    envelope = _ler_envelope(response)
    if not envelope or envelope.get("intencao") != "Consultar lista de compras":
        return response
    for evidence in reversed(evidencias):
        if evidence.get("ferramenta") != "get_list":
            continue
        try:
            lists = json.loads(evidence.get("conteudo", ""))
        except (ValueError, TypeError):
            return response
        if not isinstance(lists, list) or not lists or not all(isinstance(item, dict) for item in lists):
            return response
        if len(lists) == 1:
            envelope = {"dominio": "events", "intencao": "Consultar lista de compras",
                        "resposta": "Esta é sua lista de compras.", "lista": lists[0]}
        else:
            choices = []
            for i, item in enumerate(lists, 1):
                items = item.get("array_list") or []
                if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
                    return response
                names = ", ".join(str(x.get("name", "")) for x in items[:3]) or "sem itens"
                choices.append(f"{i}) {item.get('title', 'Lista')} — {names}")
            envelope = {"dominio": "events", "intencao": "Consultar lista de compras",
                        "resposta": "Encontrei estas listas (da mais recente para a mais antiga):\n" + "\n".join(choices),
                        "acompanhamento": "Qual delas você deseja consultar? Pode indicar o número."}
        return json.dumps(envelope, ensure_ascii=False)
    return response


def _formatar_lista(lista) -> str:
    if not isinstance(lista, dict):
        return ""
    title = str(lista.get("titulo") or lista.get("title") or "").strip()
    items = lista.get("itens", lista.get("array_list"))
    if not title or not isinstance(items, list):
        return ""
    lines = [title]
    for item in items:
        if not isinstance(item, dict):
            return ""
        name = str(item.get("nome") or item.get("name") or "").strip()
        quantity = item.get("quantidade", item.get("quantity"))
        unit = str(item.get("unidade") or item.get("unitOfMeasure") or "").strip()
        if not name or quantity is None:
            return ""
        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)
        checked = item.get("comprado", item.get("checked", False))
        lines.append(f"- {name}: {quantity} {unit}".rstrip() + (" (comprado)" if checked else ""))
    if not items:
        lines.append("A lista está vazia.")
    return "\n".join(lines)


def _montar_sem_modelo(resposta_agente: str, saudou: bool = False) -> str:
    """
    Monta o texto final a partir do envelope, sem chamar o orquestrador.

    Serve para a rota de FAQ, que nao tem juiz nem dado de dominio para
    compor: o envelope ja traz a frase pronta e o orquestrador so a repetia,
    cobrando uma chamada inteira por isso. Devolve string vazia quando o
    envelope nao da para aproveitar — ai o orquestrador assume, como antes.
    """

    dados = _ler_envelope(resposta_agente)

    if dados is None:
        return ""

    abertura = f"{SAUDACAO_CURTA} " if saudou else ""

    esclarecer = str(dados.get("esclarecer") or "").strip()

    # Pergunta de clarificacao encerra a mensagem e anda sozinha.
    if esclarecer:
        return f"{abertura}{esclarecer}"

    partes = [str(dados.get("resposta") or "").strip()]
    receita = _formatar_receita(dados.get("receita"))
    lista = _formatar_lista(dados.get("lista"))
    if dados.get("receita") and not receita:
        return "Não consegui recuperar a receita completa. Qual receita você deseja consultar?"
    if receita:
        obj = dados["receita"]
        steps = obj.get("instructions") or obj.get("instrucoes") or ""
        if isinstance(steps, list):
            steps = "\n".join(str(step) for step in steps)
        missing = ingredientes_basicos_ausentes(obj.get("ingredients") or obj.get("ingredientes") or [], steps)
        if missing:
            return ("A receita está incompleta: o preparo usa " + ", ".join(missing) +
                    " sem informar as quantidades nos ingredientes. Posso completar a receita antes de você usar ou salvar?")

    if not partes[0] and not receita:
        return ""

    for campo in ("recomendacao", "acompanhamento"):
        texto = str(dados.get(campo) or "").strip()

        # Sem modelo nao da para reescrever, so da para nao repetir: entra o
        # que ainda nao foi dito.
        if texto and texto.lower() not in " ".join(partes).lower():
            partes.append(texto)

    if receita and "Ingredientes:" in partes[0] and "Modo de preparo:" in partes[0]:
        partes[0] = ""
    if receita or lista:
        blocos = (abertura + partes[0], receita or lista, " ".join(partes[1:]))

        return "\n\n".join(b.strip() for b in blocos if b.strip())

    return abertura + " ".join(partes)


@traceable(name="orquestrador", **_TRACE_NO)
def orquestrador(state: State) -> State:
    if state.get("limite_devolucoes"):
        state["resposta_final"] = (
            "Não consegui confirmar uma resposta confiável para esse pedido. "
            "Consulte os registros atuais antes de repetir uma alteração."
        )
        return state
    if state.get("juiz_aprovado"):
        rendered = _montar_sem_modelo(state.get("resposta_agente", ""), _saudou(state.get("mensagem", "")))
        if rendered:
            state["resposta_final"] = rendered
            return state
    envelope = _ler_envelope(state.get("resposta_agente", ""))
    if envelope and _formatar_lista(envelope.get("lista")) and not state.get("limite_devolucoes"):
        state["resposta_final"] = _montar_sem_modelo(state["resposta_agente"], _saudou(state.get("mensagem", "")))
        return state
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

        state["resposta_final"] = texto(resposta).strip()

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

        # Receita so passa pela parte deterministica (PII): a revisao por
        # modelo somava latencia e reescrevia a receita ja formatada.
        resultado = checar_saida(
            state["resposta_final"],
            mapa,
            revisar=(state.get("rota") != "receitas" and not state.get("lista_confirmada")
                     and not state.get("juiz_seguro") and not state.get("limite_devolucoes")),
        )

        # Bloqueio entrega a mensagem segura e encerra. Nao volta ao
        # orquestrador: ele so tem o envelope que gerou o risco e produziria o
        # mesmo texto, gastando uma chamada para repetir o problema.
        if resultado.get("bloqueado"):
            state["resposta_final"] = resultado["mensagem"]
            state["saida_bloqueada"] = True

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

        # Estado confirmado do estoque encerra a revisão vazia; não deixa o
        # acompanhamento livre oferecer uma capacidade removida do chat.
        envelope = _ler_envelope(state.get("resposta_agente", "")) or {}
        if (not resultado.get("bloqueado") and state.get("rota") == "estoque"
                and envelope.get("intencao") == "Revisar estoque"):
            stock = [e.get("conteudo") for e in state.get("evidencias", []) if e.get("ferramenta") == "get_stock"]
            if stock and stock[-1] in ("[]", "O usuário não possui nenhum produto cadastrado no estoque."):
                state["resposta_final"] = "Seu estoque está vazio. Não há itens para revisar agora."

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


def decidir_pos_eventos(state: State) -> str:
    if state.get("lista_confirmada"):
        return "guardrail_saida"
    return "juiz"


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
    tipo_erro: str | None = None,
    decisoes_juiz: list[str] | None = None,
    bloqueio_entrada: bool = False,
    bloqueio_saida: bool = False,
    judge_usage: dict | None = None,
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
        model=MODELO,
        error_type=tipo_erro,
        judge_decisions=decisoes_juiz,
        input_blocked=bloqueio_entrada,
        output_blocked=bloqueio_saida,
        judge_usage=judge_usage,
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

    if (session_id and ObjectId.is_valid(session_id)
            and not ConversationsRepository.pertence_conta(session_id, account_id)):
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")

    # Sem session_id valido, continua a ultima sessao aberta da pessoa em vez
    # de comecar do zero e esquecer a conversa.
    if not (session_id and ConversationsRepository.sessao_ativa(session_id, account_id)):
        session_id = ConversationsRepository.sessao_recente(account_id)

    if session_id:
        historico = ConversationsRepository.get_historico(
            session_id, account_id
        )
    else:
        session_id = ConversationsRepository.create_session(
            account_id
        )

        historico = []

    started_at = datetime.now(UTC)
    resultado = None
    erro = False
    tipo_erro = None

    try:
        # Tudo que o grafo chama roda dentro desta identidade: as tools leem
        # a casa e a conta daqui, e nao do que o modelo resolver repassar.
        assunto = resolver_assunto(historico, mensagem)
        if assunto:
            assunto["lista_evento"] = assunto["tipo"] == "evento" and pedido_lista_generico(mensagem)
        with identidade.da_requisicao(household_account_id, account_id, assunto=assunto), request_budget(), trace(
            name="ceris_chat_request",
            run_type="chain",
            run_id=uuid.UUID(hex=trace_id),
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
                "decisoes_juiz": [],
                "saida_bloqueada": False,
                "lista_confirmada": False,
                "juiz_aprovado": False,
                "juiz_seguro": False,
                "judge_usage": {},
            })
            if identidade.escrita_incerta():
                erro = True
                tipo_erro = "WriteUncertain"
                resultado["resposta_final"] = (
                    "Não consegui confirmar o resultado de uma alteração. "
                    "Confira os registros atuais antes de tentar novamente."
                )
    except Exception as exc:
        erro = True
        tipo_erro = type(exc).__name__

        if transient(exc):
            logger.warning("provedores indisponíveis; pedido encerrado sem retry adicional",
                           extra={"trace_id": trace_id, "stage": "workflow", "error_type": tipo_erro})
            resultado = {"resposta_final": "A IA está temporariamente indisponível. Se você pediu uma alteração, confira os registros atuais antes de repetir o pedido.",
                         "entrada_aprovada": True, "rota": "fallback"}
            if isinstance(exc, BudgetExceeded):
                resultado["resposta_final"] = "Não consegui concluir todas as etapas deste pedido. Confira os registros atuais antes de repetir uma alteração."
        else:
            logger.exception("Falha ao executar workflow", extra={"trace_id": trace_id, "stage": "workflow"})
            raise
    finally:
        finished_at = datetime.now(UTC)
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        bloqueio_entrada = resultado is not None and not resultado.get("entrada_aprovada", True)

        if bloqueio_entrada:
            erro = True
        if resultado is not None and resultado.get("limite_devolucoes"):
            erro = True
            tipo_erro = tipo_erro or "JudgeUnconfirmed"

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
            tipo_erro=tipo_erro,
            decisoes_juiz=resultado.get("decisoes_juiz", []) if resultado is not None else [],
            bloqueio_entrada=bloqueio_entrada,
            bloqueio_saida=bool(resultado.get("saida_bloqueada")) if resultado is not None else False,
            judge_usage=resultado.get("judge_usage", {}) if resultado is not None else {},
        )

    resposta = resultado["resposta_final"]

    envelope = _ler_envelope(resultado.get("resposta_agente", "")) or {}
    recipe = envelope.get("receita")
    if (resultado.get("saida_bloqueada") or envelope.get("esclarecer")
            or not _formatar_receita(recipe) or _formatar_receita(recipe) not in resposta):
        recipe = None

    ConversationsRepository.append_messages(
        session_id,
        mensagem,
        resposta,
        account_id=account_id,
        receita=recipe,
        assunto=(assunto_do_turno(historico, mensagem, envelope, recipe)
                 if resultado.get("entrada_aprovada") and not resultado.get("saida_bloqueada") else None),
        trace_id=trace_id,
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

# Receitas nao passa pelo juiz: monta o texto e vai direto para a saida.
# Mesmo criterio da FAQ: sem texto montado, o orquestrador assume.
graph.add_conditional_edges(
    "receitas",
    decidir_pos_faq,
    {
        "guardrail_saida": "guardrail_saida",
        "orquestrador": "orquestrador",
    },
)

# Pedido de cadastro ja sai respondido (texto fixo, nosso): nao ha o que
# julgar nem reescrever.
graph.add_conditional_edges(
    "estoque",
    lambda state: END if state.get("resposta_final") else "juiz",
    {
        END: END,
        "juiz": "juiz",
    },
)

graph.add_conditional_edges(
    "eventos", decidir_pos_eventos,
    {"guardrail_saida": "guardrail_saida", "juiz": "juiz"},
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
