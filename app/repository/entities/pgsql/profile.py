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

class Profile(Base):
    __tablename__="profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("address.id"))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(150))
    name: Mapped[str] = mapped_column(String(150))