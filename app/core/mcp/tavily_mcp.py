from langchain_mcp_adapters.client import MultiServerMCPClient
from ...config import TAVILY_API_KEY


if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY não definida."
        )

mcp_client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": "https://mcp.tavily.com/mcp",
            "headers": {
                "Authorization": f"Bearer {TAVILY_API_KEY}"
            },
        }
    }
)

async def load_tavily_tools():
    return await mcp_client.get_tools()
