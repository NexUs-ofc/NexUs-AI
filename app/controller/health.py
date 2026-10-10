from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from ..auth.tracing_key_validator import validate_api_key
from ..repository.mongodb.metrics import MetricsRepository
from ..repository.mongodb.traces import TracesRepository
from ..schemas.health import checar_saude, checar_vivo
from ..schemas.report import gerar_relatorio
from ..schemas.report_html import montar_html

router = APIRouter(prefix="/health")

_PAGINA = Path(__file__).resolve().parent.parent / "static" / "health" / "page.html"


@router.get("/")
def liveness():
    """
    Liveness para load balancer: responde sem tocar em dependência externa.
    """

    return checar_vivo()


@router.get("/dependencies")
def dependencies(api_key: Annotated[str, Depends(validate_api_key)]):
    """
    Estado de cada dependência externa. Exige a API key.
    """

    return checar_saude()


@router.get("/metrics")
def metrics(
    api_key: Annotated[str, Depends(validate_api_key)],
    horas: int = Query(default=24, ge=1, le=720),
):
    """
    Dados agregados para o painel do admin: p50 e p95 por rota e por nó do
    grafo, taxa de erro, custo por requisição e projeção.

    Só JSON, sem página: a interface é do painel.
    """

    return {
        "requisicoes": MetricsRepository.resumo(horas),
        "latencia_por_no": TracesRepository.latencia_por_no(horas),
    }


@router.get("/page", response_class=HTMLResponse)
def page():
    return HTMLResponse(content=_PAGINA.read_text(encoding="utf-8"))


@router.get("/report", response_class=HTMLResponse)
def report(
    api_key: Annotated[str, Depends(validate_api_key)],
    dias: int = 7,
    mensagens_semana: int = 10,
    economia_mensal_brl: float = 0.0,
    projeto: str | None = None,
):
    """
    Relatório de observabilidade a partir do LangSmith, com valores em real.
    """

    dados = gerar_relatorio(
        dias=dias,
        mensagens_semana=mensagens_semana,
        economia_mensal_brl=economia_mensal_brl,
        projeto=projeto,
    )

    return HTMLResponse(content=montar_html(dados))
