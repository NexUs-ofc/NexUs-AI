from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.pgsql.category import Category

logger = logging.getLogger(__name__)


class CategoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_name(self, category_name: str) -> Category | None:
        try:
            stmt = select(Category).where(
                func.lower(Category.category_name) == category_name.strip().lower()
            )
            return self.session.scalars(stmt).first()
        except SQLAlchemyError:
            logger.exception("Erro ao buscar categoria por nome")
            return None

    def get_or_create(self, category_name: str) -> Category | None:
        categoria = self.find_by_name(category_name)
        if categoria:
            return categoria

        try:
            categoria = Category(category_name=category_name.strip())
            self.session.add(categoria)
            self.session.flush()
            return categoria
        except SQLAlchemyError:
            logger.exception("Erro ao criar nova categoria")
            return self.find_by_name("Outros")