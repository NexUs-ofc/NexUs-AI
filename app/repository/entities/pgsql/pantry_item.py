from datetime import datetime
<<<<<<< HEAD
from sqlalchemy import DateTime, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .config import Base
from decimal import Decimal


class Pantry_Item(Base):
    __tablename__ = "pantry_item"
=======
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
    )
from .config import Base
from decimal import Decimal

class Pantry_Item(Base):
    __tablename__="pantry_item"
>>>>>>> b94b141b26db892366519398b3f7679e1bc6b3d6

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("food.id"))
    household_account_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric())
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    minimum_quantity: Mapped[Decimal] = mapped_column(Numeric())
<<<<<<< HEAD
    is_expired: Mapped[bool] = mapped_column(Boolean)
=======
    is_expired: Mapped[bool] = mapped_column(Boolean)
>>>>>>> b94b141b26db892366519398b3f7679e1bc6b3d6
