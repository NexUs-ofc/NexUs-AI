from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ...controller.config import logging
from ...model.pgsql.category import Category
from ...model.pgsql.food import Food

logger = logging.getLogger(__name__)

CATEGORIA_PADRAO = "Outros"

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

            foods = list(self.session.scalars(stmt).all())

            logger.info(f"Alimentos listados com sucesso, {len(foods)} alimentos encontrados")

            return foods

        except SQLAlchemyError:
            logger.exception("Erro ao listar alimentos")

            return []

    def buscar_por_nome(self, nome: str) -> list[Food]:
        """
        Alimentos cujo nome contém o termo, ignorando caixa.

        Devolve lista porque "leite" casa com vários: quem chama decide se há
        ambiguidade a resolver com o usuário.
        """
        try:
            stmt = (
                select(Food)
                .where(func.lower(Food.name).contains(nome.strip().lower()))
                .order_by(Food.name)
            )

            return list(self.session.scalars(stmt).all())

        except SQLAlchemyError:
            logger.exception(f"Erro ao buscar alimento por nome: {nome}")

            return []

    def garantir_categoria(self, nome: str | None) -> int | None:
        """
        Id da categoria pelo nome, criando-a se ainda não existir.

        Sem nome, cai na categoria padrão. O food.category_id é NOT NULL, então
        sempre precisa sobrar um id daqui.
        """
        alvo = (nome or CATEGORIA_PADRAO).strip()

        try:
            stmt = select(Category).where(
                func.lower(Category.category_name) == alvo.lower()
            )

            encontrada = self.session.scalars(stmt).first()

            if encontrada:
                return encontrada.id

            categoria = Category(category_name=alvo)

            self.session.add(categoria)
            self.session.flush()

            logger.info(f"Categoria criada: {alvo}")

            return categoria.id

        except SQLAlchemyError:
            logger.exception(f"Erro ao garantir categoria: {alvo}")

            return None

    def criar(
        self,
        nome: str,
        categoria: str | None = None,
        marca: str = "Genérico",
        quantidade_embalagem: Decimal | float = 1,
        unidade: str = "unit",
    ) -> Food | None:
        """
        Cadastra um alimento que ainda não existe no catálogo.

        Existe para o estoque não travar quando a pessoa cita algo fora da
        tabela: sem isto, o agente só podia insistir com o usuário ou inventar
        um food_id, que viola a FK.
        """
        try:
            categoria_id = self.garantir_categoria(categoria)

            if categoria_id is None:
                return None

            food = Food(
                name=nome.strip(),
                category_id=categoria_id,
                product_brand=marca,
                package_quantity=Decimal(str(quantidade_embalagem)),
                unit_of_measure=unidade,
            )

            self.session.add(food)
            self.session.commit()
            self.session.refresh(food)

            logger.info(f"Alimento criado: {food.name} (id={food.id})")

            return food

        except SQLAlchemyError:
            logger.exception(f"Erro ao criar alimento: {nome}")

            self.session.rollback()

            return None