from app.controller.config import logging
from app.core.agents import investigation_app
from app.guardrails.guardrails import desanonimizar
from app.observability.cost import extrair_tokens
from app.observability.tool_logging_callback import ToolLoggingCallback
from app.repository.mongodb.hallucination_replays import HallucinationReplaysRepository
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_VEREDITOS_VALIDOS = ("SUSTENTADA", "PARCIAL", "NAO_SUSTENTADA")

_LIMITE_EVIDENCIA = 500


def _normalizar_veredito(texto: str) -> str:
    limpo = (
        texto.strip()
        .upper()
        .replace("Ã", "A")
        .replace("Õ", "O")
        .replace(" ", "_")
    )

    if limpo in _VEREDITOS_VALIDOS:
        return limpo

    if limpo.startswith("NAO"):
        return "NAO_SUSTENTADA"

    if "SUSTENTADA" in limpo:
        return "SUSTENTADA"

    if "PARCIAL" in limpo:
        return "PARCIAL"

    return "PARCIAL"


def _extrair_evidencias(mensagens) -> list[str]:
    evidencias = []

    for msg in mensagens:
        if getattr(msg, "type", None) != "tool":
            continue

        conteudo = getattr(msg, "content", "")

        if not conteudo:
            continue

        evidencias.append(str(conteudo)[:_LIMITE_EVIDENCIA])

    return evidencias


def _parsear_investigacao(texto: str) -> dict:
    veredito = ""
    resposta_revisada = ""
    reivindicacoes = []
    em_resposta = False

    for linha in texto.splitlines():
        trecho = linha.strip()

        if not trecho:
            continue

        if trecho.upper().startswith("VEREDITO:"):
            veredito = _normalizar_veredito(trecho.split(":", 1)[1])
        elif trecho.upper().startswith("RESPOSTA_REVISADA"):
            em_resposta = True

            restante = trecho.split(":", 1)[1] if ":" in trecho else ""

            if restante:
                resposta_revisada = restante
        elif trecho.upper().startswith(("REIVINDICACAO", "REIVINDICAÇÃO")):
            reivindicacoes.append(trecho)
        elif em_resposta:
            resposta_revisada += "\n" + trecho

    if not veredito:
        veredito = "PARCIAL" if resposta_revisada.strip() else "SUSTENTADA"

    return {
        "veredito": veredito,
        "resposta_revisada": resposta_revisada.strip(),
        "reivindicacoes": reivindicacoes,
    }


def _invocar_investigador(
    pergunta: str,
    resposta: str,
    rota: str,
    household_account_id: int,
    account_id: int,
    trace_id: str,
    evidencias: list[str] | None = None,
) -> dict:
    linhas = [
        f"PERGUNTA={pergunta}",
        f"ROTA={rota}",
        f"RESPOSTA_CANDIDATA={resposta}",
        f"PROFILE_ID={household_account_id}",
        f"HOUSEHOLD_ID={household_account_id}",
        f"ACCOUNT_ID={account_id}",
    ]

    if evidencias:
        linhas.append(
            "EVIDENCIAS_COLETADAS: dados já retornados pelas ferramentas "
            "de verificação durante esta investigação"
        )

        for evidencia in evidencias:
            linhas.append(f"- {evidencia}")

        linhas.append(
            "Instrução de replay: reescreva a resposta usando APENAS "
            "estas evidências já coletadas; se precisar confirmar um ponto "
            "não coberto, execute a ferramenta correspondente."
        )

    resultado = investigation_app.invoke(
        {"messages": [HumanMessage(content="\n".join(linhas))]},
        config={
            "callbacks": [ToolLoggingCallback()],
            "metadata": {"trace_id": trace_id},
        },
    )

    mensagens_saida = resultado.get("messages", [])

    input_tokens = 0
    output_tokens = 0

    for msg in mensagens_saida:
        tokens_in, tokens_out = extrair_tokens(msg)
        input_tokens += tokens_in
        output_tokens += tokens_out

    texto_final = ""

    if mensagens_saida:
        texto_final = mensagens_saida[-1].content

    return {
        "resposta": texto_final,
        "evidencias": _extrair_evidencias(mensagens_saida),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def checar_alucinacao(
    pergunta: str,
    resposta: str,
    rota: str,
    mapa_pii: dict,
    trace_id: str,
    household_account_id: int,
    account_id: int,
) -> dict:
    rota_normalizada = (rota or "").strip().lower()

    if rota_normalizada == "fallback":
        logger.debug(
            "guardrail_alucinacao: rota fallback sem fatos a verificar",
            extra={"trace_id": trace_id, "stage": "hallucination_filter"},
        )

        return {
            "resposta": resposta,
            "alucinacao_detectada": False,
            "veredito": "SUSTENTADA",
            "evidencias": [],
            "replay_executado": False,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    pergunta_limpa = desanonimizar(pergunta, mapa_pii)
    resposta_candidata = desanonimizar(resposta, mapa_pii)

    investigacao = _invocar_investigador(
        pergunta=pergunta_limpa,
        resposta=resposta_candidata,
        rota=rota,
        household_account_id=household_account_id,
        account_id=account_id,
        trace_id=trace_id,
    )

    parse = _parsear_investigacao(investigacao["resposta"])

    veredito = parse["veredito"]
    evidencias = investigacao["evidencias"]
    input_tokens = investigacao["input_tokens"]
    output_tokens = investigacao["output_tokens"]

    alucinacao_detectada = veredito in ("PARCIAL", "NAO_SUSTENTADA")
    replay_executado = False
    resposta_final = resposta_candidata

    if alucinacao_detectada and parse["resposta_revisada"]:
        replay = _invocar_investigador(
            pergunta=pergunta_limpa,
            resposta=parse["resposta_revisada"],
            rota=rota,
            household_account_id=household_account_id,
            account_id=account_id,
            trace_id=trace_id,
            evidencias=evidencias,
        )

        input_tokens += replay["input_tokens"]
        output_tokens += replay["output_tokens"]

        evidencias.extend(replay["evidencias"])

        replay_parse = _parsear_investigacao(replay["resposta"])

        if replay_parse["resposta_revisada"]:
            resposta_final = replay_parse["resposta_revisada"]
            veredito = replay_parse["veredito"]
        else:
            resposta_final = parse["resposta_revisada"]

        replay_executado = True

    HallucinationReplaysRepository.save_replay(
        trace_id=trace_id,
        pergunta=pergunta_limpa,
        resposta_original=resposta_candidata,
        veredito=veredito,
        evidencias=evidencias,
        resposta_final=resposta_final,
        replay_executado=replay_executado,
    )

    logger.info(
        "guardrail_alucinacao avaliado",
        extra={
            "trace_id": trace_id,
            "stage": "hallucination_filter",
            "rota": rota,
            "veredito": veredito,
            "alucinacao_detectada": alucinacao_detectada,
            "replay_executado": replay_executado,
        },
    )

    return {
        "resposta": resposta_final,
        "alucinacao_detectada": alucinacao_detectada,
        "veredito": veredito,
        "evidencias": evidencias,
        "replay_executado": replay_executado,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }