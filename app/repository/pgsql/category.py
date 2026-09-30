from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.nota_fiscal.categoria import CategoriaProduto
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

    def get_or_create(self, categoria: CategoriaProduto) -> Category:
        """
        Resolve a categoria do ENUM na tabela `category`, criando-a se ainda
        não existir. Só aceita valores do ENUM, então o usuário/LLM não
        consegue poluir a tabela com categorias arbitrárias.

        A criação roda num SAVEPOINT: se falhar (ex.: corrida com outro
        request criando a mesma categoria), só o savepoint é desfeito e a
        transação externa continua utilizável.
        """

        nome = CategoriaProduto(categoria).value

        existente = self.find_by_name(nome)

        if existente:
            return existente

        try:
            with self.session.begin_nested():
                nova = Category(category_name=nome)
                self.session.add(nova)

            logger.info(f"Categoria '{nome}' criada")

            return nova

        except SQLAlchemyError:
            logger.exception(f"Erro ao criar categoria '{nome}', tentando reler")

            existente = self.find_by_name(nome)

            if existente is None:
                raise

            return existente
