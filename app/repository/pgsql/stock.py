from sqlalchemy import func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..entities.pgsql.category import Category
from ..entities.pgsql.food import Food
from ..entities.pgsql.pantry_item import Pantry_Item
from ...controller.config import logging

logger = logging.getLogger(__name__)


class StockRepository:

    def __init__(self, session: Session):
        self.session = session

    def get_stock(self, household_account_id: int) -> list[Pantry_Item]:
        try:
            logger.info("Buscando estoque do usuário")

            stmt = (
                select(Pantry_Item)
                .where(
                    Pantry_Item.household_account_id == household_account_id
                )
            )

            return list(self.session.scalars(stmt).all())

        except SQLAlchemyError:
            logger.exception("Erro ao listar estoque")
            return []

    def get_expired_products(
        self,
        household_account_id: int
    ) -> list[Pantry_Item]:
        try:
            logger.info("Buscando produtos vencidos")

            stmt = (
                select(Pantry_Item)
                .where(
                    Pantry_Item.household_account_id == household_account_id,
                    (
                        (Pantry_Item.expiry_date <= func.current_date() + text("INTERVAL '7 days'")) |
                        (Pantry_Item.is_expired.is_(True))
                    )
                )
            )

            return list(self.session.scalars(stmt).all())

        except SQLAlchemyError:
            logger.exception("Erro ao buscar produtos vencidos")
            return []

    def get_category_info(
        self,
        household_account_id: int
    ) -> list[Row]:
        try:
            logger.info("Gerando relatório por categoria")

            stmt = (
                select(
                    Category.category_name,
                    func.sum(Pantry_Item.quantity).label("total_products")
                )
                .join(Food, Pantry_Item.food_id == Food.id)
                .join(Category, Food.category_id == Category.id)
                .where(
                    Pantry_Item.household_account_id == household_account_id
                )
                .group_by(Category.category_name)
            )

            return self.session.execute(stmt).all()

        except SQLAlchemyError:
            logger.exception("Erro ao gerar relatório por categoria")
            return []
