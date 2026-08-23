from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from ..config import GEMINI_API_KEY, GROQ_API_KEY

gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    top_p=0.95,
    api_key=GEMINI_API_KEY
)
groq_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0.7,
    api_key=GROQ_API_KEY
)
specialist_llm = gemini_llm.with_fallbacks([groq_llm])

fast_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=GROQ_API_KEY
)