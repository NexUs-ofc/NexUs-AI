from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.pgsql.food import UNIT_OF_MEASURE_VALUES, Food

logger = logging.getLogger(__name__)

MARCA_GENERICA = "Genérico"


class FoodRepository:

    def __init__(self, session: Session):
        self.session = session

    def get_foods(self) -> list[Food]:

        try:
            logger.info("Buscando alimentos cadastrados")

            stmt = (
                select(Food)
                .order_by(Food.name)
            )

            foods = list(self.session.scalars(stmt).all())

            logger.info(f"Alimentos listados com sucesso, {len(foods)} alimentos encontrados")

            return foods

        except SQLAlchemyError:
            logger.exception("Erro ao listar alimentos")

            return []

    def find_by_name_and_brand(self, name: str, product_brand: str | None) -> Food | None:
        """
        Busca case-insensitive por nome + marca. Sem marca, procura o item
        "Genérico" — nunca casa com um produto de marca qualquer, para não
        misturar, por exemplo, "Leite" genérico com "Leite Piracanjuba".
        """

        marca = (product_brand or MARCA_GENERICA).strip().lower()

        try:
            stmt = select(Food).where(
                func.lower(Food.name) == name.strip().lower(),
                func.lower(Food.product_brand) == marca,
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
    ) -> Food:
        food = self.find_by_name_and_brand(name, product_brand)

        if food:
            return food

        unidade = unit_of_measure if unit_of_measure in UNIT_OF_MEASURE_VALUES else "unit"

        with self.session.begin_nested():
            food = Food(
                name=name.strip(),
                category_id=category_id,
                product_brand=(product_brand or MARCA_GENERICA).strip(),
                package_quantity=package_quantity if package_quantity is not None else Decimal(1),
                unit_of_measure=unidade,
            )
            self.session.add(food)

        logger.info(f"Alimento '{food.name}' ({food.product_brand}) cadastrado")

        return food
