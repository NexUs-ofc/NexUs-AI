from langchain_core.tools import tool


@tool("recomend_recipe")
def recomendar_receita(
    description: str,
    profile_id: int,
    account_id: int,
) -> str:
    """
    Recomenda uma receita com agente de receitas com base na descrição fornecida.

    Parâmetros:
        - description: Descrição geral do evento, contendo quantidade de pessoas, clima, tipo de evento e preferências ou restrições alimentares.
        - profile_id: Identificador do usuário, recebido em PROFILE_ID na entrada do agente de eventos.
        - account_id: Identificador da conta, recebido em ACCOUNT_ID na entrada do agente de eventos.

    Saída:
        - Retorna a recomendação de receita em formato JSON estruturado, contendo título, ingredientes (com quantidade escalada para qtd_pessoas), instruções e campo "ingredientes_faltantes" com o que não tem no estoque.
    """

    from ..core.agents import recipe_app

    request = f"""
        ROUTE=receitas
        CHAMADO_POR=events
        PERGUNTA_ORIGINAL=Recomende uma receita para esse evento seguindo explicitamente a sua descrição, utilizando como principal peso para essa recomendação a quantidade de pessoas, clima, preferências alimentares e o tipo do evento:\n\n{description}
        PROFILE_ID={profile_id}
        ACCOUNT_ID={account_id}
    """

    response = recipe_app.invoke({
        "messages": [{"role": "ai", "content": request}]
    })

    return response["messages"][-1].content