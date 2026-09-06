from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

from ..config import GROQ_API_KEY, GEMINI_API_KEY

groq_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0.7,
    api_key=GROQ_API_KEY
)
specialist_llm = groq_llm

fast_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=GROQ_API_KEY
)

multimodal_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0,
    google_api_key=GEMINI_API_KEY,
)