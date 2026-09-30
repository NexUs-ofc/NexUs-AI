from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from ..config import GEMINI_API_KEY, GEMINI_VISION_MODEL, GROQ_API_KEY

groq_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0.7,
    api_key=GROQ_API_KEY,
    max_retries=4,
    request_timeout=90,
)
specialist_llm = groq_llm

fast_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=GROQ_API_KEY,
    max_retries=4,
    request_timeout=90,
)

# LLM multimodal (visão) usado pelo leitor de notas fiscais.
# O modelo é configurável por env (GEMINI_VISION_MODEL) para não precisar de
# deploy quando o Google aposentar uma versão (a família 1.5 já foi desligada).
multimodal_llm = ChatGoogleGenerativeAI(
    model=GEMINI_VISION_MODEL,
    temperature=0,
    google_api_key=GEMINI_API_KEY,
    max_retries=2,
    timeout=90,
)
