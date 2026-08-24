import uvicorn

from app.controller.config import app
from app.controller.chat import router as chat_router


app.include_router(chat_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)