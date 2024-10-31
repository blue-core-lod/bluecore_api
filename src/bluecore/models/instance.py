from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Array
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from bluecore.app.database import Base, VECTOR_SIZE

import datetime

class Instance(Base):
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True)
    uri = Column(String, unique=True)
    admin_metadata = Column(Integer, ForeignKey("AdminMetadata.id"))

    group = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(JSONB)
    embedding = Column(Vector(VECTOR_SIZE))    
    work = relationship(
       "Work",
       back_populates="instances"
    )
    embeddings = relationship("InstanceEmbedding", back_populates="instance") 
    versions = relationship("InstanceVersion", back_populates="instance")
    

class InstanceEmbedding(Base):
    __tablename__ = "work_embedding"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    embedding = Column(Vector(VECTOR_SIZE))

    instance = relationship("Instance", back_populates="embeddings")
    version = relationship("InstanceVersion", back_populates="embeddings")



class InstanceVersion(Base):
    __tablename__ = "instance_version"
  
    id = Column(Integer, primary_key=True)
    resource_id = Column(String, ForeignKey('resources.id'))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user = Column(String, ForeignKey('users.id'))
    data = Column(JSONB)
    embeddings = relationship("InstanceEmbedding", back_populates="version")
    
    instance = relationship("Instances", back_populates="versions")

