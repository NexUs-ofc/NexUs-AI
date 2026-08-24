import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq


load_dotenv()


def _get_api_keys() -> tuple[str | None, str | None]:
    return os.getenv("GEMINI_API_KEY"), os.getenv("GROQ_API_KEY")


def _build_models() -> tuple[Runnable, Runnable]:
    """Cria os modelos somente quando o fluxo realmente for executado."""

    gemini_key, groq_key = _get_api_keys()

    if not gemini_key and not groq_key:
        raise RuntimeError(
            "Nenhuma chave de LLM configurada. Defina GEMINI_API_KEY ou "
            "GROQ_API_KEY no arquivo .env."
        )

    gemini = None
    groq = None

    if gemini_key:
        gemini = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            top_p=0.95,
            api_key=gemini_key,
        )

    if groq_key:
        groq = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0.7,
            api_key=groq_key,
        )

    specialist = gemini.with_fallbacks([groq]) if gemini and groq else gemini or groq

    if groq_key:
        fast = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0,
            api_key=groq_key,
        )
    else:
        fast = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            api_key=gemini_key,
        )

    return specialist, fast


@lru_cache(maxsize=1)
def _get_models() -> tuple[Runnable, Runnable]:
    return _build_models()


@lru_cache(maxsize=1)
def get_specialist_llm() -> Runnable:
    return _get_models()[0]


@lru_cache(maxsize=1)
def get_fast_llm() -> Runnable:
    return _get_models()[1]