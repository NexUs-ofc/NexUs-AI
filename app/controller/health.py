from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..auth.tracing_key_validator import validate_api_key
from ..schemas.health import checar_saude, checar_vivo

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


@router.get("/page", response_class=HTMLResponse)
def page():
    return HTMLResponse(content=_PAGINA.read_text(encoding="utf-8"))
