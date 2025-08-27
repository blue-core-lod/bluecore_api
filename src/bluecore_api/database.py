import os

from pymilvus import MilvusClient, MilvusException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


db_url = os.getenv("DATABASE_URL", "")
engine = create_engine(db_url)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

milvus_url = os.getenv("MILVUS_URI")


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def get_vector_client():
    if not milvus_url:
        client = MilvusClient("test-vector.db")  # For testing
    else:
        client = MilvusClient(uri=milvus_url)
    return client


def filter_vector_result(
    vector_client: MilvusClient, collection_name: str, version_id: int
) -> list:
    try:
        result = vector_client.query(
            collection_name=collection_name,
            filter=f"version == {version_id}",
            output_fields=["text", "vector"],
        )
        return [{"text": r["text"], "vector": r["vector"]} for r in result]
    except MilvusException as e:
        # 100: collection not found; 2000: segcore "HasRawData" on empty/growing segments
        if getattr(e, "code", None) in (100, 2000):
            return []
        raise
