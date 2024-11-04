from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from bluecore.app.database import Base, VECTOR_SIZE

import datetime

class AdminMetadata(Base):
    __tablename__ = "admin_metadata"

    id = Column(Integer, primary_key=True)
    group = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(JSONB)    
    embeddings = relationship(
        "AdminMetadatEmbedding",
        back_populates="admin_metadata"
    )
    versions = relationship(
        "AdminMetadataVersion",
        back_populates="admin_metadata"
    )


class  AdminMetadatEmbedding(Base):
    __tablename__ = "admin_metadata_embedding"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    embedding = Column(Vector(VECTOR_SIZE))

    admin_metadata = relationship(
        "AdminMetadata",
        back_populates="embeddings"
    )
    version = relationship(
        "AdminMetadataVersion",
        back_populates="embedding"
    )

class AdminMetadataVersion(Base):
    __tablename__ = "admin_metadata_version"
    id = Column(Integer, primary_key=True)
    data = Column(JSONB)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    admin_metadata = relationship(
        "AdminMetadata",
        back_populates="versions"
    )
    embedding = relationship(
      "AdminMetadatEmbedding",
      back_populates="version"
    )
