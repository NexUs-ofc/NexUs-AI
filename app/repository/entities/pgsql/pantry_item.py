from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .config import Base
from decimal import Decimal


class Pantry_Item(Base):
    __tablename__ = "pantry_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id"))
    household_account_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric())
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    minimum_quantity: Mapped[Decimal] = mapped_column(Numeric())
    is_expired: Mapped[bool] = mapped_column(Boolean)
