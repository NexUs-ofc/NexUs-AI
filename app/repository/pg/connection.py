import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
Session = sessionmaker(bind=engine)
Base = declarative_base()


def get_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()
