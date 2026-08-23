from fastapi import FastAPI
from .controller.chat import router as chat_router

app = FastAPI()

app.include_router(chat_router)

@app.get("/")
def check() -> dict:
    return {"msg":"Ceris Rodando!"}

