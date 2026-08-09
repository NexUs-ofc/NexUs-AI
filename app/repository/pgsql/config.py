from sqlalchemy import create_engine
<<<<<<< HEAD
from sqlalchemy.orm import sessionmaker
=======
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
>>>>>>> b94b141b26db892366519398b3f7679e1bc6b3d6
from dotenv import load_dotenv
import os

load_dotenv()

PGSQL_URL = os.getenv("PGSQL_URL")

engine = create_engine(PGSQL_URL, echo=False)

Sessionlocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
<<<<<<< HEAD
)
=======
)
>>>>>>> b94b141b26db892366519398b3f7679e1bc6b3d6
