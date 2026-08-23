from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from ...model.pgsql.food import Food
from ...controller.config import logging

logger = logging.getLogger(__name__)

class FoodRepository:

    def __init__(self, session):
        self.session = session

    def get_foods(self) -> list[Food]:

        try:
            logger.info("Buscando alimentos cadastrados")

            stmt = (
                select(Food)
                .order_by(Food.name)
            )

            return list(self.session.scalars(stmt).all())

        except SQLAlchemyError:
            logger.exception("Erro ao listar alimentos")

            return []