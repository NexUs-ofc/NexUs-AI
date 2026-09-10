from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .config import Base


class Pantry_Item(Base):
    __tablename__ = "pantry_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    quantity: Mapped[int] = mapped_column(Integer())
    expiry_date: Mapped[date] = mapped_column(Date())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )