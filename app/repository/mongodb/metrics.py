from datetime import UTC, datetime, timedelta

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)

# Quantas perguntas uma pessoa faz por semana. Chute explicito, usado so na
# projecao de custo: trocar aqui muda a projecao inteira.
REQUISICOES_POR_USUARIO_SEMANA = 10


def _percentil(valores: list[float], posicao: int) -> float:
    """Percentil por indice, sem numpy. Lista vazia vira zero."""

    if not valores:
        return 0.0

    ordenados = sorted(valores)
    indice = min(
        len(ordenados) - 1,
        round((posicao / 100) * (len(ordenados) - 1)),
    )

    return round(ordenados[indice], 1)


class MetricsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    metrics_collection = db.get_collection("metrics")

    @staticmethod
    def save_request_metric(
        trace_id: str,
        route: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: float,
        tool_calls: int,
        error: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
        error_type: str | None = None,
        judge_decisions: list[str] | None = None,
        input_blocked: bool = False,
        output_blocked: bool = False,
    ) -> bool:
        try:
            logger.info(f"Salvando métrica de requisição {trace_id}")

            MetricsRepository.metrics_collection.insert_one({
                "trace_id": trace_id,
                "route": route,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "tool_calls": tool_calls,
                "error": error,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "model": model,
                "error_type": error_type,
                "judge_decisions": judge_decisions or [],
                "input_blocked": input_blocked,
                "output_blocked": output_blocked,
            })

            logger.info(f"Métrica de requisição {trace_id} salva com sucesso")

            return True

        except PyMongoError:
            logger.exception(f"Erro ao salvar métrica de requisição {trace_id}")
            return False

    @staticmethod
    def listar(desde: datetime, ate: datetime) -> list[dict]:
        """
        Métricas de requisição da janela, para o painel agregar em Python.

        Volta lista vazia se o Mongo falhar: o painel mostra zero em vez de cair.
        """

        try:
            return list(
                MetricsRepository.metrics_collection.find(
                    {"started_at": {"$gte": desde, "$lt": ate}},
                    {"_id": 0},
                )
            )

        except PyMongoError:
            logger.exception("Erro ao listar métricas da janela")
            return []

    @staticmethod
    def resumo(horas: int = 24) -> dict:
        """
        Agrega as requisições da janela para o painel.

        Média esconde o que dói: p95 é a experiência de quem esperou. Erro e
        latência saem por rota, porque elas têm custo muito diferente entre si
        e uma média única não diz onde mexer.

        A projeção de custo é regra de três sobre o custo por requisição da
        janela, não previsão: serve para dimensionar, não para orçar.
        """

        desde = datetime.now(UTC) - timedelta(hours=horas)

        try:
            logger.info(f"Agregando métricas das últimas {horas}h")

            etapas = [
                {"$match": {"started_at": {"$gte": desde}}},
                {"$sort": {"duration_ms": 1}},
                {"$group": {
                    "_id": "$route",
                    "requisicoes": {"$sum": 1},
                    "erros": {"$sum": {"$cond": ["$error", 1, 0]}},
                    "duracoes": {"$push": "$duration_ms"},
                    "tokens_entrada": {"$sum": "$input_tokens"},
                    "tokens_saida": {"$sum": "$output_tokens"},
                    "custo_usd": {"$sum": "$cost_usd"},
                    "chamadas_de_tool": {"$sum": "$tool_calls"},
                }},
            ]

            por_rota = {}
            total = {"requisicoes": 0, "erros": 0, "custo_usd": 0.0}

            for linha in MetricsRepository.metrics_collection.aggregate(etapas):
                duracoes = linha.pop("duracoes", [])
                rota = linha.pop("_id") or "desconhecida"

                linha["p50_ms"] = _percentil(duracoes, 50)
                linha["p95_ms"] = _percentil(duracoes, 95)
                linha["taxa_de_erro"] = (
                    round(linha["erros"] / linha["requisicoes"], 4)
                    if linha["requisicoes"]
                    else 0.0
                )
                linha["custo_usd"] = round(linha["custo_usd"], 6)

                por_rota[rota] = linha

                total["requisicoes"] += linha["requisicoes"]
                total["erros"] += linha["erros"]
                total["custo_usd"] += linha["custo_usd"]

            custo_por_requisicao = (
                total["custo_usd"] / total["requisicoes"]
                if total["requisicoes"]
                else 0.0
            )

            return {
                "janela_horas": horas,
                "requisicoes": total["requisicoes"],
                "taxa_de_erro": (
                    round(total["erros"] / total["requisicoes"], 4)
                    if total["requisicoes"]
                    else 0.0
                ),
                "custo_usd": round(total["custo_usd"], 6),
                "custo_por_requisicao_usd": round(custo_por_requisicao, 6),
                "projecao_semanal_usd": {
                    f"{usuarios}_usuarios": round(
                        custo_por_requisicao * usuarios * REQUISICOES_POR_USUARIO_SEMANA,
                        2,
                    )
                    for usuarios in (100, 1000)
                },
                "por_rota": por_rota,
            }

        except PyMongoError:
            logger.exception("Erro ao agregar métricas")

            return {}
