from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from ..auth.admin_key_validator import validate_admin_key
from ..schemas.health import checar_saude
from ..schemas.painel import montar_painel, montar_relatorio
from ..schemas.report import gerar_relatorio

router = APIRouter(prefix="/admin", dependencies=[Depends(validate_admin_key)])


@router.get("/session")
def session():
    """
    Confirma a chave no login do painel: 200 com a chave certa, 401 sem ela.
    """

    return {
        "servico": "ceris-ia",
        "autenticado": True,
        "verificado_em": datetime.now(UTC).isoformat(timespec="seconds"),
    }


@router.get("/metrics")
def metrics(dias: int = Query(default=7, ge=1, le=90)):
    """
    A página da IA no painel: resumo, desempenho, leitura de nota, custo e
    qualidade, a partir do que o grafo grava no Mongo. Rápida: não consulta o
    LangSmith.
    """

    return montar_painel(dias)


@router.get("/report")
def report(dias: int = Query(default=7, ge=1, le=90)):
    """
    Relatório do período: indicadores contra o período anterior de mesmo
    tamanho, as rotas mais lentas e as tools que mais falham.
    """

    return montar_relatorio(dias)


@router.get("/langsmith")
def langsmith(
    dias: int = Query(default=7, ge=1, le=90),
    mensagens_semana: int = 10,
    economia_mensal_brl: float = 0.0,
    projeto: str | None = None,
):
    """
    Seção do LangSmith: execuções e erros por dia, latência por chain e por
    agente, feedback e custo em real. Lenta, porque pagina a API do LangSmith:
    o painel carrega à parte.
    """

    return gerar_relatorio(
        dias=dias,
        mensagens_semana=mensagens_semana,
        economia_mensal_brl=economia_mensal_brl,
        projeto=projeto,
    )


@router.get("/dependencies")
def dependencies():
    """
    Estado de cada dependência externa e consumo do processo.
    """

    return checar_saude()
