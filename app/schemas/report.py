import math
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests

from app.config import (
    LANGCHAIN_API_KEY,
    LANGCHAIN_PROJECT,
    LANGSMITH_WORKSPACE_ID,
)
from app.controller.config import logging

logger = logging.getLogger(__name__)

LANGSMITH_URL = "https://api.smith.langchain.com"
PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{data}'&$format=json"
)

NOME_RAIZ = "ceris_chat_request"

NOS_AGENTES = [
    "agente_faq",
    "agente_receitas",
    "agente_estoque",
    "agente_eventos",
]

NOS_PIPELINE = [
    "guardrail_entrada",
    "roteador",
    "orquestrador",
    "guardrail_saida",
]

TIMEOUT = 60
PAGINA = 100
MAX_PAGINAS = 50
MAX_TENTATIVAS = 5
PAUSA_ENTRE_PAGINAS = 0.4


def _requisitar(metodo: str, caminho: str, **kwargs) -> requests.Response:
    """
    Chama a API do LangSmith com backoff para o 429 dela.
    """

    espera = 2.0

    for tentativa in range(MAX_TENTATIVAS):
        resposta = requests.request(
            metodo,
            f"{LANGSMITH_URL}{caminho}",
            headers=_cabecalhos(),
            timeout=TIMEOUT,
            **kwargs,
        )

        if resposta.status_code != 429:
            resposta.raise_for_status()
            return resposta

        if tentativa == MAX_TENTATIVAS - 1:
            resposta.raise_for_status()

        pausa = float(resposta.headers.get("Retry-After") or espera)
        logger.warning(f"LangSmith respondeu 429, aguardando {pausa:.1f}s")
        time.sleep(pausa)
        espera = min(espera * 2, 30.0)

    raise RuntimeError("LangSmith recusou a consulta após várias tentativas")


def _cabecalhos() -> dict:
    cabecalhos = {"x-api-key": LANGCHAIN_API_KEY}

    if LANGSMITH_WORKSPACE_ID:
        cabecalhos["X-Tenant-Id"] = LANGSMITH_WORKSPACE_ID

    return cabecalhos


def _id_do_projeto(projeto: str) -> str | None:
    resposta = _requisitar("GET", "/sessions", params={"name": projeto, "limit": 1})
    encontrados = resposta.json()

    return encontrados[0]["id"] if encontrados else None


def _buscar_runs(projeto_id: str, inicio: datetime) -> list[dict]:
    runs = []
    cursor = None

    for _ in range(MAX_PAGINAS):
        corpo = {
            "session": [projeto_id],
            "start_time": inicio.isoformat(),
            "limit": PAGINA,
            "select": [
                "name",
                "run_type",
                "status",
                "error",
                "start_time",
                "end_time",
                "trace_id",
                "parent_run_id",
                "dotted_order",
                "extra",
                "total_cost",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            ],
        }

        if cursor:
            corpo["cursor"] = cursor

        resposta = _requisitar("POST", "/runs/query", json=corpo)
        pagina = resposta.json()
        lote = pagina.get("runs", [])
        runs.extend(lote)

        cursor = (pagina.get("cursors") or {}).get("next")

        if not cursor or not lote:
            break

        time.sleep(PAUSA_ENTRE_PAGINAS)

    logger.info(f"Relatório coletou {len(runs)} runs do projeto {projeto_id}")

    return runs


def _cotacao_dolar() -> dict:
    hoje = datetime.now(timezone.utc).date()

    for atraso in range(8):
        dia = hoje - timedelta(days=atraso)

        try:
            resposta = requests.get(
                PTAX_URL.format(data=dia.strftime("%m-%d-%Y")),
                timeout=TIMEOUT,
            )
            resposta.raise_for_status()
            valores = resposta.json().get("value", [])
        except Exception:
            logger.exception("Erro ao consultar a PTAX")
            break

        if valores:
            return {
                "data": dia.isoformat(),
                "venda": float(valores[0]["cotacaoVenda"]),
                "fonte": "PTAX / Banco Central do Brasil",
            }

    return {"data": None, "venda": None, "fonte": "indisponível"}


def _duracao(run: dict) -> float | None:
    if not run.get("start_time") or not run.get("end_time"):
        return None

    inicio = datetime.fromisoformat(run["start_time"].replace("Z", "+00:00"))
    fim = datetime.fromisoformat(run["end_time"].replace("Z", "+00:00"))

    return (fim - inicio).total_seconds()


def _percentil(amostras: list[float], fracao: float) -> float:
    if not amostras:
        return 0.0

    indice = math.ceil(len(amostras) * fracao) - 1

    return amostras[min(len(amostras) - 1, max(0, indice))]


def _metadados(run: dict) -> dict:
    return (run.get("extra") or {}).get("metadata") or {}


def _deduplicar(runs: list[dict]) -> list[dict]:
    """
    O LangGraph cria uma run por nó com o mesmo nome dos nossos spans.
    Mantém a mais externa de cada par (dotted_order mais curto).
    """

    melhores: dict[tuple, dict] = {}

    for run in runs:
        chave = (run.get("trace_id"), run.get("name"))
        atual = melhores.get(chave)

        if atual is None or len(run.get("dotted_order") or "") < len(atual.get("dotted_order") or ""):
            melhores[chave] = run

    return list(melhores.values())


def _resumo_latencia(runs: list[dict], nomes: list[str]) -> list[dict]:
    por_nome: dict[str, list[float]] = {}

    for run in _deduplicar(runs):
        if run.get("name") not in nomes:
            continue

        duracao = _duracao(run)

        if duracao is not None:
            por_nome.setdefault(run["name"], []).append(duracao)

    resultado = []

    for nome, amostras in por_nome.items():
        amostras.sort()
        resultado.append({
            "nome": nome,
            "chamadas": len(amostras),
            "media_s": round(statistics.mean(amostras), 2),
            "mediana_s": round(statistics.median(amostras), 2),
            "p95_s": round(_percentil(amostras, 0.95), 2),
        })

    return sorted(resultado, key=lambda item: -item["media_s"])


def gerar_relatorio(
    dias: int = 7,
    mensagens_semana: int = 10,
    economia_mensal_brl: float = 0.0,
    projeto: str | None = None,
) -> dict:
    """
    Reúne no LangSmith as métricas exigidas e converte os valores para real.
    """

    projeto = projeto or LANGCHAIN_PROJECT
    inicio = datetime.now(timezone.utc) - timedelta(days=dias)

    projeto_id = _id_do_projeto(projeto)

    if not projeto_id:
        return {
            "erro": f"Projeto '{projeto}' não encontrado no LangSmith.",
            "projeto": projeto,
        }

    runs = _buscar_runs(projeto_id, inicio)
    cotacao = _cotacao_dolar()
    taxa = cotacao.get("venda")

    def em_real(valor_usd: float) -> float | None:
        return round(valor_usd * taxa, 4) if taxa else None

    raizes = [r for r in runs if r.get("name") == NOME_RAIZ and not r.get("parent_run_id")]
    llms = [r for r in runs if r.get("run_type") == "llm"]

    duracoes = sorted(d for d in (_duracao(r) for r in raizes) if d is not None)
    com_erro = [r for r in raizes if r.get("status") == "error"]

    custo_usd = sum(float(r.get("total_cost") or 0) for r in llms)
    tokens_entrada = sum(int(r.get("prompt_tokens") or 0) for r in llms)
    tokens_saida = sum(int(r.get("completion_tokens") or 0) for r in llms)

    total_requisicoes = len(raizes)
    custo_medio_usd = custo_usd / total_requisicoes if total_requisicoes else 0.0

    sessoes = {
        _metadados(r).get("session_id")
        for r in raizes
        if _metadados(r).get("session_id")
    }

    custo_por_resolucao_usd = custo_usd / len(sessoes) if sessoes else 0.0

    cenarios = []

    for usuarios in (100, 1000):
        semanal_usd = custo_medio_usd * mensagens_semana * usuarios
        cenarios.append({
            "usuarios": usuarios,
            "mensagens_semana": mensagens_semana * usuarios,
            "semanal_usd": round(semanal_usd, 4),
            "semanal_brl": em_real(semanal_usd),
            "mensal_usd": round(semanal_usd * 4, 4),
            "mensal_brl": em_real(semanal_usd * 4),
        })

    custo_mensal_household_usd = custo_medio_usd * mensagens_semana * 4
    custo_mensal_household_brl = em_real(custo_mensal_household_usd)

    roi_pct = None

    if economia_mensal_brl and custo_mensal_household_brl:
        roi_pct = round(
            ((economia_mensal_brl - custo_mensal_household_brl) / custo_mensal_household_brl) * 100,
            1,
        )

    modelos: dict[str, int] = {}

    for run in llms:
        modelo = _metadados(run).get("ls_model_name") or "desconhecido"
        modelos[modelo] = modelos.get(modelo, 0) + 1

    return {
        "projeto": projeto,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodo": {
            "dias": dias,
            "inicio": inicio.isoformat(timespec="seconds"),
        },
        "cotacao": cotacao,
        "requisicoes": {
            "total": total_requisicoes,
            "com_erro": len(com_erro),
            "taxa_erro_pct": round(len(com_erro) / total_requisicoes * 100, 1) if total_requisicoes else 0.0,
            "runs_coletadas": len(runs),
        },
        "tempo_total": {
            "media_s": round(statistics.mean(duracoes), 2) if duracoes else 0.0,
            "mediana_s": round(statistics.median(duracoes), 2) if duracoes else 0.0,
            "p95_s": round(_percentil(duracoes, 0.95), 2) if duracoes else 0.0,
            "min_s": round(duracoes[0], 2) if duracoes else 0.0,
            "max_s": round(duracoes[-1], 2) if duracoes else 0.0,
        },
        "agentes": _resumo_latencia(runs, NOS_AGENTES),
        "etapas": _resumo_latencia(runs, NOS_PIPELINE),
        "custo": {
            "chamadas_llm": len(llms),
            "tokens_entrada": tokens_entrada,
            "tokens_saida": tokens_saida,
            "total_usd": round(custo_usd, 6),
            "total_brl": em_real(custo_usd),
            "por_requisicao_usd": round(custo_medio_usd, 6),
            "por_requisicao_brl": em_real(custo_medio_usd),
            "modelos": modelos,
        },
        "projecao": {
            "mensagens_semana": mensagens_semana,
            "cenarios": cenarios,
        },
        "resolucao": {
            "sessoes": len(sessoes),
            "mensagens_por_sessao": round(total_requisicoes / len(sessoes), 1) if sessoes else 0.0,
            "custo_usd": round(custo_por_resolucao_usd, 6),
            "custo_brl": em_real(custo_por_resolucao_usd),
        },
        "roi": {
            "economia_mensal_brl": economia_mensal_brl or None,
            "custo_mensal_brl": custo_mensal_household_brl,
            "roi_pct": roi_pct,
        },
        "erros": [
            {
                "quando": r.get("start_time", "")[:19],
                "detalhe": (r.get("error") or "sem detalhe").splitlines()[0][:200],
            }
            for r in com_erro[:8]
        ],
    }
