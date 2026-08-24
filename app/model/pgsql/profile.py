from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .config import Base

class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("address.id"))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(150))