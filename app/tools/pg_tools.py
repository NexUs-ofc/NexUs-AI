from datetime import date, timedelta
from langchain.tools import tool
from app.repository.pg.connection import Session
from app.repository.pg.models import PantryItem, Food, Category


@tool("consultar_estoque")
def consultar_estoque(household_account_id: int) -> str:
    """Consulta os itens do estoque de um usuário pelo household_account_id."""
    session = Session()
    try:
        itens = (
            session.query(PantryItem, Food, Category)
            .join(Food, PantryItem.food_id == Food.id)
            .join(Category, Food.category_id == Category.id)
            .filter(PantryItem.household_account_id == household_account_id)
            .all()
        )

        if not itens:
            return "Nenhum item encontrado no estoque."

        linhas = []
        for pantry, food, cat in itens:
            linhas.append(
                f"- {food.name} | Categoria: {cat.category_name} | "
                f"Qtd: {pantry.quantity} {pantry.unit_of_measure} | "
                f"Validade: {pantry.expiry_date} | Status: {pantry.status}"
            )
        return "\n".join(linhas)
    finally:
        session.close()


@tool("consultar_itens_proximos_vencimento")
def consultar_itens_proximos_vencimento(household_account_id: int, dias: int = 7) -> str:
    """Consulta itens do estoque que vencem nos próximos X dias."""
    session = Session()
    try:
        limite = date.today() + timedelta(days=dias)
        hoje = date.today()

        itens = (
            session.query(PantryItem, Food)
            .join(Food, PantryItem.food_id == Food.id)
            .filter(
                PantryItem.household_account_id == household_account_id,
                PantryItem.expiry_date <= limite,
                PantryItem.expiry_date >= hoje,
            )
            .all()
        )

        if not itens:
            return "Nenhum item próximo do vencimento."

        linhas = []
        for pantry, food in itens:
            linhas.append(
                f"- {food.name} | Qtd: {pantry.quantity} {pantry.unit_of_measure} | "
                f"Vence em: {pantry.expiry_date}"
            )
        return "\n".join(linhas)
    finally:
        session.close()
