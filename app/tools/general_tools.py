from langchain_core.tools import tool
from ..core.agents import recipe_app

@tool("recomend_recipe")
def recomendar_receita(
    description:str,
) -> str:
    """
    Recomenda uma receita com agente de receitas com base na descrição fornecida.

    Parâmetros:
        - description: Descrição geral do evento, contendo quantidade de pessoas, clima, tipo de evento e preferências ou restrições alimentares.

    Saída:
        - Retorna a recomendação de receita em formato JSON estruturado, contendo título, ingredientes (com quantidade escalada para qtd_pessoas), instruções e campo "ingredientes_faltantes" com o que não tem no estoque.
    """

    request = f"""
        ROUTE=receitas
        CHAMADO_POR=events
        PERGUNTA_ORIGINAL=Recomende uma receita para esse evento seguindo explicitamente a sua descrição, utilizando como principal peso para essa recomendação a quantidade de pessoas, clima, preferências alimentares e o tipo do evento:\n\n{description}
    """

    response = recipe_app.invoke({
        "messages": [{"role":"ai", "content":request}]
    })

    return response["messages"][-1].content

