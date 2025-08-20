import os

from pymilvus import MilvusClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


db_url = os.getenv("DATABASE_URL", "")
engine = create_engine(db_url, )
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

milvus_url = os.getenv("MILVUS_URI")

def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def get_vector_db():
    if not milvus_url:
        client = MilvusClient("test-vector.db")  # For testing
    else:
        client = MilvusClient(uri=milvus_url)
    return client
