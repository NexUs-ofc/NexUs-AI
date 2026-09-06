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
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "30"))
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
VALID_API_KEYS = set(
    key.strip() for key in os.getenv("VALID_API_KEYS", "").split(",") if key.strip()
)
 