import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


db_url = os.getenv("DATABASE_URL", "")
engine = create_engine(db_url)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def get_session_maker():
    return Session
