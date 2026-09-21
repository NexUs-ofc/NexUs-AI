from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from ..auth.dependencies import get_current_user
from ..config import TRACING_API_KEY
from ..schemas.metrics import build_cost_summary, build_summary

router = APIRouter(prefix="/metrics")

_DASHBOARD_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "metrics" / "dashboard.html"


def _verificar_auth(authorization: str | None) -> None:
    esperado = f"Bearer {TRACING_API_KEY}"

    if not authorization or authorization != esperado:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/summary")
def get_summary(user: Annotated[dict, Depends(get_current_user)]):
    return build_summary()


@router.get("/cost")
def get_cost(
    user: Annotated[dict, Depends(get_current_user)],
    requests_per_user_per_week: int = 20,
    value_per_resolution_usd: float = 0.0,
):
    return build_cost_summary(requests_per_user_per_week, value_per_resolution_usd)


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    return HTMLResponse(content=_DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
