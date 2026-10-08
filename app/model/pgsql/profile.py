from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .config import Base


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Integer, e nao ForeignKey: a tabela referenciada nao e mapeada neste
    # projeto, e a FK declarada quebraria a configuracao do mapper. A
    # constraint existe no banco.
    address_id: Mapped[int] = mapped_column(Integer())
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(150))