from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .config import Base


class Pantry_Item(Base):
    __tablename__ = "pantry_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id"))
    household_account_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric())
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    minimum_quantity: Mapped[Decimal] = mapped_column(Numeric())
    is_expired: Mapped[bool] = mapped_column(Boolean)