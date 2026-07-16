from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from .llms import fast_llm
from ..tools.faq_tools import faq_retriever
from .prompts.prompt_faqs import FAQ_PROMPT_COMPLETO

load_dotenv('.env')


faq_app = create_agent(
    model=fast_llm,
    tools=[faq_retriever],
    system_prompt=FAQ_PROMPT_COMPLETO,
)

