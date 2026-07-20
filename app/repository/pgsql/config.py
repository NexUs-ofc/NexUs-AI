from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

PGSQL_URL = os.getenv("PGSQL_URL")

engine = create_engine(PGSQL_URL, echo=False)

Sessionlocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)