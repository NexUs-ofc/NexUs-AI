from langchain.tools import tool
from app.repository.pgsql.config import Sessionlocal
from app.repository.pgsql.stock import StockRepository
from app.repository.entities.pgsql.pantry_item import Pantry_Item


@tool("consultar_estoque")
def consultar_estoque(household_account_id: int) -> str:
    """Consulta os itens do estoque de um usuário pelo household_account_id."""

    with Sessionlocal() as session:
        repo = StockRepository(session)
        itens = repo.get_stock(household_account_id)

        if not itens:
            return "Nenhum item encontrado no estoque."

        linhas = []
        for item in itens:
            linhas.append(
                f"- ID:{item.food_id} | "
                f"Qtd: {item.quantity} | "
                f"Validade: {item.expiry_date} | "
                f"Vencido: {'Sim' if item.is_expired else 'Não'}"
            )
        return "\n".join(linhas)


@tool("consultar_itens_proximos_vencimento")
def consultar_itens_proximos_vencimento(household_account_id: int) -> str:
    """Consulta itens do estoque vencidos ou próximos do vencimento (7 dias)."""

    with Sessionlocal() as session:
        repo = StockRepository(session)
        itens = repo.get_expired_products(household_account_id)

        if not itens:
            return "Nenhum item próximo do vencimento."

        linhas = []
        for item in itens:
            linhas.append(
                f"- ID:{item.food_id} | "
                f"Qtd: {item.quantity} | "
                f"Vence em: {item.expiry_date}"
            )
        return "\n".join(linhas)
