from fastapi import APIRouter

from ..schemas.health import checar_vivo

router = APIRouter(prefix="/health")


@router.get("/")
def liveness():
    """
    Liveness para load balancer: responde sem tocar em dependência externa.

    O resto do que era /health (dependências, métricas e relatório) mudou
    para /admin, atrás da chave do painel.
    """

    return checar_vivo()
