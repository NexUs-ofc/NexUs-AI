import os

from dotenv import load_dotenv

load_dotenv()
 
MONGODB_URI = os.getenv("MONGODB_URI")
PGSQL_URL = os.getenv("PGSQL_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
QDRANT_DATABASE_URL = os.getenv("QDRANT_DATABASE_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
DOC_FILE_PATH = os.getenv("DOC_FILE_PATH")
FAQ_FILE_PATH = os.getenv("FAQ_FILE_PATH")
TRACING_API_KEY = os.getenv("TRACING_API_KEY")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY não definida. Configure a mesma chave usada pelo "
        "microsserviço de autenticação; sem ela os tokens não podem ser validados."
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "30"))
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
VALID_API_KEYS = {
    key.strip() for key in os.getenv("VALID_API_KEYS", "").split(",") if key.strip()
}

LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "ceris-ms-ia")
LANGSMITH_WORKSPACE_ID = os.getenv("LANGSMITH_WORKSPACE_ID")

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY

if LANGSMITH_WORKSPACE_ID:
    os.environ["LANGSMITH_WORKSPACE_ID"] = LANGSMITH_WORKSPACE_ID
 