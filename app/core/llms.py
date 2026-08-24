from langchain_groq import ChatGroq

from ..config import GROQ_API_KEY

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