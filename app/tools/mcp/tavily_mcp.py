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
            # tools/list e uma dependência opcional no startup. Limite a conexão
            # e o stream para que um MCP indisponível não prenda o processo.
            "timeout": 5,
            "sse_read_timeout": 5,
            "headers": {
                "Authorization": f"Bearer {TAVILY_API_KEY}"
            },
        }
    }
)

async def load_tavily_tools():
    return await mcp_client.get_tools()
