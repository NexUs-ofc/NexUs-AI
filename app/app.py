from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .controller.chat import router as chat_router
from .controller.health import router as health_router
from .controller.nota_fiscal import router as nota_fiscal_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(health_router, tags=["Health"])
app.include_router(nota_fiscal_router, tags=["Nota Fiscal"])

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

@app.get("/")
def check() -> dict:
    return {"msg":"Ceris.AI Rodando!"}
