from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ...config import PGSQL_URL

# O Aiven fecha conexao ociosa. Sem o pre_ping, o pool entregava uma conexao
# ja morta e a primeira consulta depois de um tempo parado falhava com "server
# closed the connection unexpectedly" - e a Cerita dizia que nao conseguia ver
# o estoque. O recycle troca a conexao antes de o servidor derruba-la.
engine = create_engine(PGSQL_URL, echo=False, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)