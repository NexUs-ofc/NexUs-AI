from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .config import Base

UNIT_OF_MEASURE_VALUES = ("kg", "g", "l", "ml", "unit")


class Food(Base):
    __tablename__ = "food"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    product_brand: Mapped[str] = mapped_column(String(100))
    package_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_of_measure: Mapped[str] = mapped_column(
        Enum(*UNIT_OF_MEASURE_VALUES, name="unit_of_measure_enum", create_type=False)
    )