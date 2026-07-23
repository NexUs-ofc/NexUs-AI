import logging
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/")
def check():
    logger.info("Requisição em \"/\" feita com sucesso!")
    return {
        "status": 200,
        "msg": "Ceris rodando com sucesso!"
    }
