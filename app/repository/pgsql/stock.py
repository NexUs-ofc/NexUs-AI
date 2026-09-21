from sqlalchemy import func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.pgsql.category import Category
from ...model.pgsql.food import Food
from ...model.pgsql.pantry_item import Pantry_Item
from ...model.pgsql.pantry_product_setting import Pantry_Product_Setting

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

            item = self.session.get(Pantry_Item, pantry_item_id)

            logger.info(f"Busca de item concluída, encontrado={item is not None}")

            return item

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

    def get_stock(self, profile_id: int) -> list[Pantry_Item]:
        try:
            logger.info("Buscando estoque do usuário")

            stmt = (
                select(Pantry_Item)
                .where(
                    Pantry_Item.profile_id == profile_id
                )
            )

            itens = list(self.session.scalars(stmt).all())

            logger.info(f"Estoque listado com sucesso, {len(itens)} itens encontrados")

            return itens

        except SQLAlchemyError:
            logger.exception("Erro ao listar estoque")

            return []

    def get_expired_products(
        self,
        profile_id: int
    ) -> list[Pantry_Item]:
        try:
            logger.info("Buscando produtos vencidos")

            stmt = (
                select(Pantry_Item)
                .where(
                    Pantry_Item.profile_id == profile_id,
                    Pantry_Item.expiry_date <= func.current_date() + text("INTERVAL '7 days'")
                )
            )

            itens = list(self.session.scalars(stmt).all())

            logger.info(f"Produtos vencidos listados com sucesso, {len(itens)} itens encontrados")

            return itens

        except SQLAlchemyError:
            logger.exception("Erro ao buscar produtos vencidos")

            return []

    def get_missing_products(
        self,
        profile_id: int
    ) -> list[Row]:
        try:
            logger.info("Buscando produtos em falta")

            stmt = (
                select(
                    Pantry_Item.food_id,
                    func.sum(Pantry_Item.quantity).label("quantity"),
                    Pantry_Product_Setting.minimum_quantity,
                )
                .join(
                    Pantry_Product_Setting,
                    (Pantry_Product_Setting.food_id == Pantry_Item.food_id)
                    & (Pantry_Product_Setting.profile_id == Pantry_Item.profile_id)
                )
                .where(
                    Pantry_Item.profile_id == profile_id
                )
                .group_by(
                    Pantry_Item.food_id,
                    Pantry_Product_Setting.minimum_quantity
                )
                .having(
                    func.sum(Pantry_Item.quantity)
                    < Pantry_Product_Setting.minimum_quantity
                )
            )

            rows = self.session.execute(stmt).all()

            logger.info(f"Produtos em falta listados com sucesso, {len(rows)} itens encontrados")

            return rows

        except SQLAlchemyError:
            logger.exception("Erro ao buscar produtos em falta")

            return []

    def get_category_info(
        self,
        profile_id: int
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
                    Pantry_Item.profile_id == profile_id
                )
                .group_by(
                    Category.category_name
                )
            )

            rows = self.session.execute(stmt).all()

            logger.info(f"Relatório por categoria gerado com sucesso, {len(rows)} categorias")

            return rows

        except SQLAlchemyError:
            logger.exception("Erro ao gerar relatório por categoria")

            return []

    def get_brand_info(
        self,
        profile_id: int
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
                    Pantry_Item.profile_id == profile_id
                )
                .group_by(
                    Food.product_brand
                )
            )

            rows = self.session.execute(stmt).all()

            logger.info(f"Relatório por marca gerado com sucesso, {len(rows)} marcas")

            return rows

        except SQLAlchemyError:
            logger.exception("Erro ao gerar relatório por marca")

            return []