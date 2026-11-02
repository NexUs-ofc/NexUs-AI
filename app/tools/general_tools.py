from langchain_core.tools import tool


@tool("recomend_recipe")
def recomendar_receita(
    description: str,
) -> str:
    """
    Recomenda uma receita com agente de receitas com base na descrição fornecida.

    Parâmetros:
        - description: Descrição geral do evento, contendo quantidade de pessoas, clima, tipo de evento e preferências ou restrições alimentares.

    Saída:
        - Retorna a recomendação de receita em formato JSON estruturado, contendo título, ingredientes (com quantidade escalada para qtd_pessoas), instruções e campo "ingredientes_faltantes" com o que não tem no estoque.
    """


    # Import aqui dentro: agents importa esta tool, e no topo seria circular.
    import logging

    from langgraph.errors import GraphRecursionError

    from ..auth import identidade
    from ..core.agents import AGENTES_DAS_SKILLS
    from ..core.runtime_budget import AGENT_RECURSION_LIMIT
    from ..schemas.flow import _restricoes_prontas

    assunto = identidade.assunto() or {}
    contexto = ""
    if assunto.get("tipo") == "evento":
        import json
        contexto = "\nCONTEXTO_DO_EVENTO=" + json.dumps(assunto, ensure_ascii=False, default=str)

    restrictions = _restricoes_prontas(identidade.perfil())
    if restrictions.startswith("FALHA"):
        return "FALHA: não foi possível conferir as restrições alimentares; não gere receita sem essa consulta."
    request = f"""
        ROUTE=receitas
        CHAMADO_POR=events
        RESTRICOES={restrictions}
        PERGUNTA_ORIGINAL=Recomende uma receita para esse evento seguindo explicitamente a sua descrição, utilizando como principal peso para essa recomendação a quantidade de pessoas, clima, preferências alimentares e o tipo do evento:\n\n{description}
    """

    request += contexto
    try:
        response = AGENTES_DAS_SKILLS["receita-para-evento"].invoke(
            {"messages": [{"role": "user", "content": request}]},
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )
    except GraphRecursionError:
        logging.getLogger(__name__).warning(
            "GraphRecursionError no agente de receita chamado pelo evento",
            extra={"stage": "agent", "recursion_limit": AGENT_RECURSION_LIMIT},
        )
        return "FALHA: a recomendação excedeu o limite de etapas; não repita a mesma chamada."

    from ..core.llms import texto

    return texto(response["messages"][-1])
