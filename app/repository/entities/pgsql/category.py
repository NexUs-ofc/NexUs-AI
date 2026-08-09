<<<<<<< HEAD
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .config import Base


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_name: Mapped[str] = mapped_column(String(100))
=======
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    )
from .config import Base

class Category(Base):
    __tablename__="category"

    id : Mapped[int] = mapped_column(primary_key=True)
    category_name : Mapped[str] = mapped_column(String(100))
>>>>>>> b94b141b26db892366519398b3f7679e1bc6b3d6
