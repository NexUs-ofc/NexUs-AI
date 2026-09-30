from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.pgsql.food import Food

logger = logging.getLogger(__name__)


class FoodRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_foods(self) -> list[Food]:
        try:
            stmt = select(Food).order_by(Food.name)
            return list(self.session.scalars(stmt).all())
        except SQLAlchemyError:
            logger.exception("Erro ao listar alimentos")
            return []

    def find_by_name_and_brand(
        self, name: str, product_brand: str | None = None
    ) -> Food | None:
        try:
            stmt = select(Food).where(
                func.lower(Food.name) == name.strip().lower()
            )
            if product_brand:
                stmt = stmt.where(
                    func.lower(Food.product_brand) == product_brand.strip().lower()
                )
            return self.session.scalars(stmt).first()
        except SQLAlchemyError:
            logger.exception("Erro ao buscar alimento por nome e marca")
            return None

    def get_or_create(
        self,
        name: str,
        category_id: int,
        product_brand: str | None = None,
        package_quantity: Decimal | None = None,
        unit_of_measure: str = "unit",
    ) -> Food | None:
        food = self.find_by_name_and_brand(name, product_brand)
        if food:
            return food

        try:
            food = Food(
                name=name.strip(),
                category_id=category_id,
                product_brand=product_brand.strip() if product_brand else "Genérico",
                package_quantity=package_quantity if package_quantity is not None else Decimal("1.0"),
                unit_of_measure=unit_of_measure if unit_of_measure in ("kg", "g", "l", "ml", "unit") else "unit",
            )
            self.session.add(food)
            self.session.flush()
            return food
        except SQLAlchemyError:
            logger.exception("Erro ao criar alimento")
            return None