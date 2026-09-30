from langchain.tools import tool

from app.repository.qdrant.preferences_repository import PreferencesRepository


@tool("consultar_preferencias")
def consultar_preferencias(account_id: int, pergunta_atual: str) -> str:
    """Consulta as preferências que o usuário registrou: gostos, restrições
    alimentares, tamanho das porções e qualquer outra instrução permanente.

    Use ANTES de sugerir receitas, montar listas de compras ou dimensionar
    eventos, para personalizar a resposta e não violar restrições.
    NÃO use para consultar estoque ou receitas salvas — para isso existem as
    tools específicas.

    Args:
        account_id: identificador da conta do usuário.
        pergunta_atual: pedido do usuário, usado para recuperar as preferências
            semanticamente mais próximas.
    """

    preferencias = PreferencesRepository.buscar_preferencias(
        account_id=account_id,
        busca=pergunta_atual,
        limite=5,
    )

    if not preferencias:
        return "Nenhuma preferência registrada para este usuário."

    return "\n".join(f"- {item}" for item in preferencias)
