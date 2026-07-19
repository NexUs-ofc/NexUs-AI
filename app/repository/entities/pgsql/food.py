from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
    )
from .config import Base
from decimal import Decimal

class Food(Base):
    __tablename__ = "food"

    id : Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    category_id : Mapped[int] = mapped_column(ForeignKey("category.id"))
    product_brand : Mapped[str] = mapped_column(String(100))
    weight : Mapped[Decimal] = mapped_column(Numeric())
