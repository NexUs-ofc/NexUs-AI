from sqlalchemy import func, select
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

    def save(self, pantry_item: Pantry_Item) -> Pantry_Item | None:
        try:
            logger.info("Tentativa de inserção de item em estoque")

            self.session.add(pantry_item)
            self.session.commit()
            self.session.refresh(pantry_item)

            logger.info("Item inserido com sucesso")

            return pantry_item

        except SQLAlchemyError:
            self.session.rollback()

            logger.exception("Erro ao inserir item em estoque")

            return None

    def find_by_id(self, pantry_item_id: int) -> Pantry_Item | None:
        try:
            logger.info("Buscando item do estoque")

            return self.session.get(Pantry_Item, pantry_item_id)

        except SQLAlchemyError:
            logger.exception("Erro ao buscar item do estoque")

            return None

    def remove_product(self, pantry_item: Pantry_Item) -> bool:
        try:
            logger.info("Tentativa de remoção de item do estoque")

            self.session.delete(pantry_item)
            self.session.commit()

            logger.info("Produto removido com sucesso")

            return True

        except SQLAlchemyError:
            self.session.rollback()

            logger.exception("Erro ao remover produto do estoque")

            return False

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
                        (Pantry_Item.expiry_date <= func.current_date()) |
                        (Pantry_Item.is_expired.is_(True))
                    )
                )
            )

            return list(self.session.scalars(stmt).all())

        except SQLAlchemyError:
            logger.exception("Erro ao buscar produtos vencidos")

            return []


    def get_missing_products(
        self,
        household_account_id: int
    ) -> list[Row]:
        try:
            logger.info("Buscando produtos em falta")

            stmt = (
                select(
                    Pantry_Item.food_id,
                    func.max(Pantry_Item.household_account_id).label(
                        "household_account_id"
                    ),
                    func.sum(Pantry_Item.quantity).label(
                        "quantity"
                    )
                )
                .where(
                    Pantry_Item.household_account_id == household_account_id,
                    Pantry_Item.is_expired.is_(False)
                )
                .group_by(
                    Pantry_Item.food_id,
                    Pantry_Item.minimum_quantity
                )
                .having(
                    func.sum(Pantry_Item.quantity)
                    < Pantry_Item.minimum_quantity
                )
            )

            return self.session.execute(stmt).all()

        except SQLAlchemyError:
            logger.exception("Erro ao buscar produtos em falta")

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
                    func.sum(Pantry_Item.quantity).label(
                        "total_products"
                    )
                )
                .join(
                    Food,
                    Pantry_Item.food_id == Food.id
                )
                .join(
                    Category,
                    Food.category_id == Category.id
                )
                .where(
                    Pantry_Item.household_account_id == household_account_id
                )
                .group_by(
                    Category.category_name
                )
            )

            return self.session.execute(stmt).all()

        except SQLAlchemyError:
            logger.exception("Erro ao gerar relatório por categoria")

            return []

    def get_brand_info(
        self,
        household_account_id: int
    ) -> list[Row]:
        try:
            logger.info("Gerando relatório por marca")

            stmt = (
                select(
                    Food.product_brand,
                    func.sum(Pantry_Item.quantity).label(
                        "total_products"
                    )
                )
                .join(
                    Food,
                    Pantry_Item.food_id == Food.id
                )
                .where(
                    Pantry_Item.household_account_id == household_account_id
                )
                .group_by(
                    Food.product_brand
                )
            )

            return self.session.execute(stmt).all()

        except SQLAlchemyError:
            logger.exception("Erro ao gerar relatório por marca")

            return []