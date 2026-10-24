import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...controller.config import logging
from ...model.pgsql.profile import Profile
from .stock import ConsultaIndisponivel

logger = logging.getLogger(__name__)

_SEPARADORES = re.compile(r"[,;\n]")


def _normalizar(valor) -> list[str]:
    """Aceita a coluna como texto ("lactose, gluten") ou como array."""

    if not valor:
        return []

    if isinstance(valor, str):
        itens = _SEPARADORES.split(valor)
    else:
        itens = list(valor)

    return [str(item).strip() for item in itens if str(item).strip()]


class ProfileRepository:

    def __init__(self, session: Session):
        self.session = session

    def get_restrictions(self, profile_id: int) -> list[str]:
        """
        Restricoes alimentares registradas no perfil.

        Lista vazia quer dizer que o perfil nao tem restricao. Falha na
        consulta levanta ConsultaIndisponivel; quem chama (flow) trata como
        "sem restricao", sem perguntar a pessoa.
        """

        try:
            logger.info(f"Buscando restricoes do perfil {profile_id}")

            valor = self.session.scalar(
                select(Profile.dietary_restrictions).where(Profile.id == profile_id)
            )

            restricoes = _normalizar(valor)

            logger.info(f"Perfil {profile_id} tem {len(restricoes)} restricoes")

            return restricoes

        except SQLAlchemyError as erro:
            logger.exception(f"Erro ao buscar restricoes do perfil {profile_id}")

            raise ConsultaIndisponivel("buscar as restricoes do perfil") from erro
