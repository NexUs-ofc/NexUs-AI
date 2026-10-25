"""
Agregações do painel do administrador.

Tudo sai das coleções que o grafo já grava no Mongo (metrics, traces e
tool_metrics): nenhuma ida ao LangSmith aqui, para a página abrir em segundos.
O que só existe no LangSmith — execuções por chain, feedback — fica em
/admin/langsmith, que é lento de propósito.

A agregação é em Python e não em pipeline do Mongo: uma semana são alguns
milhares de documentos, e assim a mesma função serve para o período atual e
para o anterior do relatório, e é testável sem banco.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone

from app.repository.mongodb.metrics import MetricsRepository, _percentil
from app.repository.mongodb.tool_metrics import ToolMetricsRepository
from app.repository.mongodb.traces import TracesRepository

# Fuso fixo de Brasília (sem horário de verão desde 2019): o "dia" do painel é
# o dia de quem usa o app, não o dia UTC. Offset fixo evita depender do tzdata.
BRASILIA = timezone(timedelta(hours=-3), "BRT")

ROTA_NOTA = "nota_fiscal"

# Cota diária do plano livre do Groq. É a linha de limite do gráfico de tokens.
LIMITE_DIARIO_TOKENS = 200_000

# Métricas gravadas antes de o campo existir não dizem o modelo; até então
# todos os nós do grafo rodavam neste.
MODELO_PADRAO = "openai/gpt-oss-20b"

ERROS_DE_COTA = {"RateLimitError"}

DECISOES_JUIZ = ("aprovado", "devolvido", "revertido")

# Spans do grafo agrupados nas etapas que o gráfico empilha. O span do agente
# leva o nome da rota.
GRUPO_DO_SPAN = {
    "guardrail_entrada": "guardrails",
    "guardrail_saida": "guardrails",
    "roteador": "roteador",
    "juiz": "juiz",
    "orquestrador": "orquestrador",
    "estoque": "agente",
    "receitas": "agente",
    "eventos": "agente",
    "faq": "agente",
    "saudacao": "agente",
}

ETAPAS = ("roteador", "agente", "juiz", "guardrails", "orquestrador")


def _pct(parte: float, total: float) -> float:
    return round(parte / total * 100, 2) if total else 0.0


def _segundos(ms: float) -> float:
    return round(ms / 1000, 2)


def _utc(momento: datetime) -> datetime:
    """O pymongo devolve datetime sem fuso, em UTC."""

    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _dia(momento: datetime) -> str:
    return _utc(momento).astimezone(BRASILIA).date().isoformat()


def _dias_da_janela(inicio: datetime, fim: datetime) -> list[str]:
    primeiro = _utc(inicio).astimezone(BRASILIA).date()
    ultimo = _utc(fim).astimezone(BRASILIA).date()

    return [
        (primeiro + timedelta(days=n)).isoformat()
        for n in range((ultimo - primeiro).days + 1)
    ]


def _do_chat(metricas: list[dict]) -> list[dict]:
    return [m for m in metricas if m.get("route") != ROTA_NOTA]


def _decisoes(chat: list[dict]) -> list[str]:
    return [d for m in chat for d in (m.get("judge_decisions") or [])]


def resumo(chat: list[dict], metricas: list[dict]) -> dict:
    """Os cinco números do topo da página."""

    duracoes = [m.get("duration_ms", 0.0) for m in chat]
    erros = sum(1 for m in chat if m.get("error"))
    decisoes = _decisoes(chat)

    return {
        "execucoes": len(chat),
        "p50_e2e_s": _segundos(_percentil(duracoes, 50)),
        "p95_e2e_s": _segundos(_percentil(duracoes, 95)),
        "custo_usd": round(sum(m.get("cost_usd", 0.0) for m in metricas), 4),
        "taxa_erro_pct": _pct(erros, len(chat)),
        "devolucoes_juiz_pct": _pct(decisoes.count("devolvido"), len(decisoes)),
    }


def latencia_por_rota(chat: list[dict]) -> list[dict]:
    """p50 e p95 ponta a ponta de cada rota, da mais lenta para a mais rápida."""

    por_rota: dict[str, list[dict]] = defaultdict(list)

    for metrica in chat:
        por_rota[metrica.get("route") or "desconhecida"].append(metrica)

    linhas = []

    for rota, lista in por_rota.items():
        duracoes = [m.get("duration_ms", 0.0) for m in lista]
        linhas.append({
            "rota": rota,
            "execucoes": len(lista),
            "erros": sum(1 for m in lista if m.get("error")),
            "p50_s": _segundos(_percentil(duracoes, 50)),
            "p95_s": _segundos(_percentil(duracoes, 95)),
        })

    return sorted(linhas, key=lambda linha: linha["p95_s"], reverse=True)


def latencia_por_no(chat: list[dict], spans: list[dict]) -> list[dict]:
    """
    Quanto cada etapa custa em média, por rota: a soma das etapas é a média
    ponta a ponta, não a soma de percentis.

    O span do agente, do juiz e do orquestrador pode aparecer duas vezes na
    mesma requisição (devolução do juiz); entra a soma, que é o que a pessoa
    esperou.
    """

    rota_do_trace = {m["trace_id"]: m.get("route") for m in chat if m.get("trace_id")}
    por_trace: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for span in spans:
        trace_id = span.get("trace_id")
        grupo = GRUPO_DO_SPAN.get(span.get("span_name"))

        if trace_id in rota_do_trace and grupo:
            por_trace[trace_id][grupo] += span.get("duration_ms", 0.0)

    por_rota: dict[str, list[dict[str, float]]] = defaultdict(list)

    for trace_id, etapas in por_trace.items():
        por_rota[rota_do_trace[trace_id] or "desconhecida"].append(etapas)

    linhas = []

    for rota, execucoes in por_rota.items():
        medias = {
            etapa: _segundos(sum(e.get(etapa, 0.0) for e in execucoes) / len(execucoes))
            for etapa in ETAPAS
        }
        linhas.append({
            "rota": rota,
            "execucoes": len(execucoes),
            "etapas_s": medias,
            "total_s": round(sum(medias.values()), 2),
        })

    return sorted(linhas, key=lambda linha: linha["total_s"], reverse=True)


def leitura_nota(notas: list[dict]) -> dict:
    duracoes = [m.get("duration_ms", 0.0) for m in notas]
    sucesso = sum(1 for m in notas if not m.get("error"))

    return {
        "leituras": len(notas),
        "sucesso": sucesso,
        "taxa_sucesso_pct": _pct(sucesso, len(notas)),
        "tempo_medio_s": _segundos(sum(duracoes) / len(duracoes)) if duracoes else 0.0,
        "p95_s": _segundos(_percentil(duracoes, 95)),
    }


def tokens_por_dia(metricas: list[dict], inicio: datetime, fim: datetime) -> dict:
    """Entrada e saída por dia e por rota, contra a cota diária do Groq."""

    dias = {
        dia: {"dia": dia, "entrada": 0, "saida": 0, "total": 0, "por_rota": {}}
        for dia in _dias_da_janela(inicio, fim)
    }

    for metrica in metricas:
        linha = dias.get(_dia(metrica["started_at"]))

        if linha is None:
            continue

        entrada = int(metrica.get("input_tokens", 0) or 0)
        saida = int(metrica.get("output_tokens", 0) or 0)
        rota = metrica.get("route") or "desconhecida"

        linha["entrada"] += entrada
        linha["saida"] += saida
        linha["total"] += entrada + saida

        por_rota = linha["por_rota"].setdefault(rota, {"entrada": 0, "saida": 0})
        por_rota["entrada"] += entrada
        por_rota["saida"] += saida

    lista = list(dias.values())
    pico = max(lista, key=lambda linha: linha["total"]) if lista else None

    return {
        "limite_diario": LIMITE_DIARIO_TOKENS,
        "total_entrada": sum(linha["entrada"] for linha in lista),
        "total_saida": sum(linha["saida"] for linha in lista),
        "pico": {
            "dia": pico["dia"],
            "total": pico["total"],
            "pct_do_limite": _pct(pico["total"], LIMITE_DIARIO_TOKENS),
        } if pico else None,
        "dias": lista,
    }


def custo_por_dia(metricas: list[dict], inicio: datetime, fim: datetime) -> dict:
    dias = {dia: {"dia": dia, "total_usd": 0.0, "por_modelo": {}} for dia in _dias_da_janela(inicio, fim)}
    por_modelo: dict[str, float] = defaultdict(float)

    for metrica in metricas:
        linha = dias.get(_dia(metrica["started_at"]))
        custo = float(metrica.get("cost_usd", 0.0) or 0.0)

        if linha is None or not custo:
            continue

        modelo = metrica.get("model") or MODELO_PADRAO
        linha["total_usd"] += custo
        linha["por_modelo"][modelo] = linha["por_modelo"].get(modelo, 0.0) + custo
        por_modelo[modelo] += custo

    for linha in dias.values():
        linha["total_usd"] = round(linha["total_usd"], 6)
        linha["por_modelo"] = {m: round(v, 6) for m, v in linha["por_modelo"].items()}

    return {
        "total_usd": round(sum(por_modelo.values()), 6),
        "por_modelo": {m: round(v, 6) for m, v in por_modelo.items()},
        "dias": list(dias.values()),
    }


def erros_de_cota(metricas: list[dict], fim: datetime) -> dict:
    """
    Requisições que terminaram em 429 do Groq, hora a hora nas últimas 24h.

    Conta só o 429 que chegou ao fim: os que o retry do cliente absorveu viram
    latência, não erro, e não aparecem aqui.
    """

    inicio = _utc(fim) - timedelta(hours=24)
    horas = {}

    for n in range(24):
        hora = (inicio + timedelta(hours=n + 1)).astimezone(BRASILIA).replace(minute=0, second=0, microsecond=0)
        horas[hora.isoformat()] = 0

    total_janela = 0

    for metrica in metricas:
        if metrica.get("error_type") not in ERROS_DE_COTA:
            continue

        total_janela += 1
        momento = _utc(metrica["started_at"])

        if momento > inicio:
            chave = momento.astimezone(BRASILIA).replace(minute=0, second=0, microsecond=0).isoformat()
            if chave in horas:
                horas[chave] += 1

    return {
        "total_24h": sum(horas.values()),
        "total_janela": total_janela,
        "por_hora": [{"hora": hora, "quantidade": n} for hora, n in horas.items()],
    }


def juiz(chat: list[dict]) -> dict:
    decisoes = _decisoes(chat)
    total = len(decisoes)

    return {
        "total": total,
        **{
            decisao: {"quantidade": decisoes.count(decisao), "pct": _pct(decisoes.count(decisao), total)}
            for decisao in DECISOES_JUIZ
        },
    }


def guardrails(chat: list[dict]) -> dict:
    entrada = sum(1 for m in chat if m.get("input_blocked"))
    saida = sum(1 for m in chat if m.get("output_blocked"))

    return {
        "execucoes": len(chat),
        "entrada": entrada,
        "saida": saida,
        "total": entrada + saida,
        "pct": _pct(entrada + saida, len(chat)),
    }


def ferramentas(chamadas: list[dict]) -> list[dict]:
    por_tool: dict[str, list[dict]] = defaultdict(list)

    for chamada in chamadas:
        por_tool[chamada.get("tool_name") or "desconhecida"].append(chamada)

    linhas = []

    for nome, lista in por_tool.items():
        duracoes = [c.get("duration_ms", 0.0) for c in lista]
        erros = sum(1 for c in lista if not c.get("success", True))
        linhas.append({
            "tool": nome,
            "chamadas": len(lista),
            "erros": erros,
            "taxa_erro_pct": _pct(erros, len(lista)),
            "media_ms": round(sum(duracoes) / len(duracoes), 1),
            "p95_ms": round(_percentil(duracoes, 95), 1),
        })

    return sorted(linhas, key=lambda linha: linha["chamadas"], reverse=True)


def _janela(dias: int, fim: datetime | None = None) -> tuple[datetime, datetime]:
    fim = fim or datetime.now(UTC)
    return fim - timedelta(days=dias), fim


def montar_painel(dias: int = 7, fim: datetime | None = None) -> dict:
    """A página da IA no painel, menos a seção do LangSmith."""

    inicio, fim = _janela(dias, fim)

    metricas = MetricsRepository.listar(inicio, fim)
    chat = _do_chat(metricas)
    notas = [m for m in metricas if m.get("route") == ROTA_NOTA]
    spans = TracesRepository.listar(inicio, fim)
    chamadas = ToolMetricsRepository.listar(inicio, fim)

    return {
        "servico": "ceris-ia",
        "janela": {
            "inicio": inicio.isoformat(timespec="seconds"),
            "fim": fim.isoformat(timespec="seconds"),
            "dias": dias,
        },
        "resumo": resumo(chat, metricas),
        "desempenho": {
            "latencia_por_rota": latencia_por_rota(chat),
            "latencia_por_no": latencia_por_no(chat, spans),
        },
        "leitura_nota": leitura_nota(notas),
        "custo": {
            "tokens": tokens_por_dia(metricas, inicio, fim),
            "custo": custo_por_dia(metricas, inicio, fim),
            "erros_de_cota": erros_de_cota(metricas, fim),
        },
        "qualidade": {
            "juiz": juiz(chat),
            "guardrails": guardrails(chat),
            "ferramentas": ferramentas(chamadas),
        },
    }


def _variacao(atual: float, anterior: float, em_pontos: bool) -> float | None:
    if em_pontos:
        return round(atual - anterior, 2)

    return round((atual - anterior) / anterior * 100, 2) if anterior else None


def _indicadores(chat: list[dict], metricas: list[dict]) -> dict:
    numeros = resumo(chat, metricas)

    return {
        "volume": numeros["execucoes"],
        "latencia_p95_e2e_s": numeros["p95_e2e_s"],
        "custo_usd": numeros["custo_usd"],
        "taxa_erro_pct": numeros["taxa_erro_pct"],
        "devolucoes_juiz_pct": numeros["devolucoes_juiz_pct"],
    }


# (chave, unidade, variação em pontos percentuais e não em %)
INDICADORES = (
    ("volume", "execucoes", False),
    ("latencia_p95_e2e_s", "s", False),
    ("custo_usd", "usd", False),
    ("taxa_erro_pct", "%", True),
    ("devolucoes_juiz_pct", "%", True),
)


def montar_relatorio(dias: int = 7, fim: datetime | None = None) -> dict:
    """
    Resumo do período comparado com o período anterior de mesmo tamanho.

    Variação de volume, latência e custo é percentual; de taxa de erro e de
    devolução do juiz é em pontos percentuais, porque já são percentuais.
    """

    inicio, fim = _janela(dias, fim)
    inicio_anterior = inicio - timedelta(days=dias)

    metricas = MetricsRepository.listar(inicio, fim)
    anteriores = MetricsRepository.listar(inicio_anterior, inicio)
    chat = _do_chat(metricas)
    chamadas = ToolMetricsRepository.listar(inicio, fim)

    atual = _indicadores(chat, metricas)
    anterior = _indicadores(_do_chat(anteriores), anteriores)

    tools_com_erro = sorted(
        (linha for linha in ferramentas(chamadas) if linha["erros"]),
        key=lambda linha: (linha["taxa_erro_pct"], linha["chamadas"]),
        reverse=True,
    )

    tokens = tokens_por_dia(metricas, inicio, fim)

    return {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "periodo_atual": {"inicio": inicio.isoformat(timespec="seconds"), "fim": fim.isoformat(timespec="seconds")},
        "periodo_anterior": {
            "inicio": inicio_anterior.isoformat(timespec="seconds"),
            "fim": inicio.isoformat(timespec="seconds"),
        },
        "indicadores": [
            {
                "indicador": chave,
                "unidade": unidade,
                "atual": atual[chave],
                "anterior": anterior[chave],
                "variacao": _variacao(atual[chave], anterior[chave], em_pontos),
                "variacao_em": "pontos" if em_pontos else "pct",
            }
            for chave, unidade, em_pontos in INDICADORES
        ],
        "rotas_mais_lentas": latencia_por_rota(chat)[:3],
        "tools_com_mais_erro": tools_com_erro[:3],
        "consumo": {
            "tokens_entrada": tokens["total_entrada"],
            "tokens_saida": tokens["total_saida"],
            "pico_diario": tokens["pico"],
            "limite_diario": LIMITE_DIARIO_TOKENS,
        },
        "leitura_nota": leitura_nota([m for m in metricas if m.get("route") == ROTA_NOTA]),
        "juiz": juiz(chat),
    }
