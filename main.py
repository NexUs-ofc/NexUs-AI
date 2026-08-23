import uvicorn
from app.controller.config import app
import app.controller.chat  # registra o endpoint

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)