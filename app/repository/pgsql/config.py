from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ...config import PGSQL_URL

engine = create_engine(PGSQL_URL, echo=False)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)