import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from groq import APIConnectionError, APIStatusError, RateLimitError

from .controller.chat import router as chat_router
from .controller.health import router as health_router
from .controller.receipt import router as receipt_router

logger = logging.getLogger(__name__)

app = FastAPI()


@app.on_event("startup")
def esquentar_conexoes() -> None:
    """
    Abre as conexões antes da primeira pergunta.

    A primeira chamada de get_stock levava 4,0–4,6s contra 0,8s nas seguintes:
    não era a consulta, era o handshake de TCP e TLS com o Aiven e o Atlas. A
    pessoa pagava isso na primeira pergunta de cada rota.

    Cada banco vai no seu try: subir sem um deles e falhar na requisição é
    melhor do que não subir.
    """

    # Sob pytest nao aquece: a suite nao toca rede, e abrir conexao aqui a
    # fazia bater no Aiven e no Atlas a cada TestClient — 25s a mais por
    # rodada, sem testar nada. Checa sys.modules e nao PYTEST_CURRENT_TEST,
    # que so existe durante um teste: o TestClient nasce na importacao.
    if "pytest" in sys.modules:
        return

    from .observability.background import avisar, em_segundo_plano

    def postgres() -> None:
        from sqlalchemy import text

        from .repository.pgsql.config import SessionLocal

        with SessionLocal() as sessao:
            sessao.execute(text("SELECT 1"))

    def mongo() -> None:
        # Cada repositorio tem o SEU MongoClient, e o pymongo conecta de forma
        # preguicosa: sem isto, o primeiro uso de cada um paga ~1s de handshake
        # separado. Sao os quatro que ficam no caminho de uma requisicao.
        from .repository.mongodb.conversations import ConversationsRepository
        from .repository.mongodb.metrics import MetricsRepository
        from .repository.mongodb.tool_metrics import ToolMetricsRepository
        from .repository.mongodb.traces import TracesRepository

        for repositorio in (
            TracesRepository,
            ToolMetricsRepository,
            MetricsRepository,
            ConversationsRepository,
        ):
            repositorio.client.admin.command("ping")

    def aquecer(nome, abrir) -> None:
        try:
            abrir()
            avisar("info", f"conexao com {nome} aquecida")
        except Exception:  # noqa: BLE001 - o avisar() abaixo registra com exc_info
            avisar(
                "warning",
                f"nao foi possivel aquecer {nome}; a primeira requisicao paga "
                f"o handshake",
                exc_info=True,
            )

    for nome, abrir in (("postgres", postgres), ("mongodb", mongo)):
        em_segundo_plano(aquecer, nome, abrir)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RateLimitError)
def limite_do_groq(request: Request, exc: RateLimitError) -> JSONResponse:
    """
    Cota do Groq estourada chegava como 500 opaco, indistinguível de bug.
    O 429 aqui carrega o motivo, para o mobile e o log dizerem o que houve.
    """

    return JSONResponse(
        status_code=429,
        content={
            "detalhe": "Cota de uso do modelo esgotada.",
            "origem": "groq",
            "mensagem_do_provedor": str(exc),
        },
    )


@app.exception_handler(APIConnectionError)
def falha_de_conexao(
    request: Request,
    exc: APIConnectionError,
) -> JSONResponse:
    """
    Rede ou DNS caindo no meio da requisição também virava 500 sem pista.
    """

    return JSONResponse(
        status_code=503,
        content={
            "detalhe": "Não foi possível falar com o provedor do modelo.",
            "origem": "groq",
            "mensagem_do_provedor": str(exc),
        },
    )


@app.exception_handler(APIStatusError)
def erro_do_provedor(
    request: Request,
    exc: APIStatusError,
) -> JSONResponse:
    """
    Qualquer outra recusa do provedor — 400 de schema de ferramenta, 401 de
    chave, 5xx deles. Virava 500 nosso, sem dizer de quem era a culpa.
    """

    return JSONResponse(
        status_code=502,
        content={
            "detalhe": "O provedor do modelo recusou a requisição.",
            "origem": "groq",
            "mensagem_do_provedor": str(exc),
        },
    )


@app.exception_handler(Exception)
def falha_inesperada(request: Request, exc: Exception) -> JSONResponse:
    """
    Ultimo recurso: banco fora, ferramenta quebrada, qualquer coisa nao
    prevista. O cliente recebia "Internal Server Error" sem nenhuma pista,
    e o mobile nao tinha como distinguir disso de um bug dele.

    O detalhe tecnico fica no log, nao na resposta.
    """

    logger.exception(
        "Falha nao tratada na requisicao",
        extra={"stage": "http", "caminho": str(request.url.path)},
    )

    return JSONResponse(
        status_code=500,
        content={
            "detalhe": "Nao foi possivel concluir a requisicao.",
            "origem": "ceris-ia",
            "tipo": type(exc).__name__,
        },
    )


app.include_router(chat_router)
app.include_router(receipt_router)
app.include_router(health_router, tags=["Health"])

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

@app.get("/")
def check() -> dict:
    return {"msg":"Ceris.AI Rodando!"}
