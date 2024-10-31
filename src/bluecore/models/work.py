from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Array
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from bluecore.app.database import Base, VECTOR_SIZE

import datetime


class Work(Base):
    __tablename__ = "works"

    id = Column(String, primary_key=True)
    uri = Column(String, unique=True)
    admin_metadata = Column(Integer, ForeignKey("AdminMetadata.id"))

    group = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(JSONB)
     
        
    instances = relationship(
       "Instances",
       back_populates="work",
       order_by="Instance.id",
       lazy="joined"
    )

    embeddings = relationship("WorkEmbedding", back_populates="work")
    versions = relationship("WorkVersion", back_populates="work")
    

class WorkEmbedding(Base):
    __tablename__ = "work_embedding"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    embedding = Column(Vector(VECTOR_SIZE))

    work = relationship("Work", back_populates="embeddings")
    version = relationship("WorkVersion", back_populates="embedding")
    

class WorkVersion(Base):
    __tablename__ = "work_versions"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    admin_metadata = Column(Integer, ForeignKey('AdminMetadataVersion.id'))
    user = Column(String, ForeignKey('users.id'))
    data = Column(JSONB)
    embeddings = relationship("WorkEmbedding", back_populates="embedding")
    
    work = relationship("Work", back_populates="versions")
