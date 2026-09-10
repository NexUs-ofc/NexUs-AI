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
 