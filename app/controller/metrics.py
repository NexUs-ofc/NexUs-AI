from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse

from ..config import TRACING_API_KEY
from ..schemas.metrics import build_summary, build_cost_summary
from ..auth.dependencies import get_current_user

router = APIRouter(prefix="/metrics")

_DASHBOARD_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "metrics" / "dashboard.html"


def _verificar_auth(authorization: str | None) -> None:
    esperado = f"Bearer {TRACING_API_KEY}"

    if not authorization or authorization != esperado:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/summary")
def get_summary(user: dict = Depends(get_current_user)):
    return build_summary()


@router.get("/cost")
def get_cost(
    user: dict = Depends(get_current_user),
    requests_per_user_per_week: int = 20,
    value_per_resolution_usd: float = 0.0,
):
    return build_cost_summary(requests_per_user_per_week, value_per_resolution_usd)


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    return HTMLResponse(content=_DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))
