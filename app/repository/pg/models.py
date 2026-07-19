from sqlalchemy import Column, Integer, String, Decimal, Date, ForeignKey, VARCHAR
from sqlalchemy.orm import relationship
from .connection import Base


class Category(Base):
    __tablename__ = "category"

    id = Column(Integer, primary_key=True)
    category_name = Column(VARCHAR(255))

    foods = relationship("Food", back_populates="category")


class Food(Base):
    __tablename__ = "food"

    id = Column(Integer, primary_key=True)
    name = Column(VARCHAR(255))
    category_id = Column(Integer, ForeignKey("category.id"))
    product_barcode = Column(VARCHAR)
    weight = Column(Decimal)

    category = relationship("Category", back_populates="foods")
    pantry_items = relationship("PantryItem", back_populates="food")


class PantryItem(Base):
    __tablename__ = "pantry_item"

    id = Column(Integer, primary_key=True)
    food_id = Column(Integer, ForeignKey("food.id"))
    household_account_id = Column(Integer)
    quantity = Column(Decimal)
    expiry_date = Column(Date)
    minimum_quantity = Column(Decimal)
    unit_of_measure = Column(VARCHAR)
    status = Column(VARCHAR)

    food = relationship("Food", back_populates="pantry_items")
