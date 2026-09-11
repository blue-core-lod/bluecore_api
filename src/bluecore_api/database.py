import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

db_url = os.getenv("DATABASE_URL", "")

# Connection pool sizing. This API shares its Postgres with Airflow, the
# workflows' bluecore tasks, and Keycloak, reached through an on-prem PgBouncer
# in the deployed stacks. SQLAlchemy's defaults hold pool_size connections open
# for the life of the process and never revalidate them, so under a session-mode
# pooler they pin server connections other clients then wait for. Keep this
# small and let the pooler do the multiplexing.
POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "5"))
MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "5"))
# Recycle connections older than this (seconds), and check liveness on checkout,
# so a connection PgBouncer or Postgres has already closed is never handed out.
POOL_RECYCLE: int = int(os.getenv("DATABASE_POOL_RECYCLE", "1800"))

engine = create_engine(
    db_url,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=True,
)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def get_session_maker():
    return Session
