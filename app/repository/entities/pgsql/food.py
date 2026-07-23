from sqlalchemy import String, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from .config import Base
from decimal import Decimal


class Food(Base):
    __tablename__ = "food"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    product_brand: Mapped[str] = mapped_column(String(100))
    weight: Mapped[Decimal] = mapped_column(Numeric())
