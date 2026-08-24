from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .config import Base


class Food(Base):
    _tablename_ = "food"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    product_brand: Mapped[str] = mapped_column(String(100))
    weight: Mapped[Decimal] = mapped_column(Numeric())