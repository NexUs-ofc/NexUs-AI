from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .controller.chat import router as chat_router
from .controller.metrics import router as metrics_router

app = FastAPI()

app.include_router(chat_router)
app.include_router(metrics_router, tags=["Metrics"])

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

@app.get("/")
def check() -> dict:
    return {"msg":"Ceris Rodando!"}

