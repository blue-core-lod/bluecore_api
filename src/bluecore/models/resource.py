from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Array
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from bluecore.app.database import Base
import datetime

VECTOR_SIZE = 128 # Use ColBert embedding size


class AdminMetadata(Base):
    __tablename__ = "admin_metadata"

    id = Column(Integer, primary_key=True)
    group = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(JSONB)    
    embedding = Column(Vector(VECTOR_SIZE))


class AdminMetadataVersion(Base):
    __tablename__ = "admin_metadata_version"
    id = Column(Integer, primary_key=True)
    data = Column(JSONB)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    embedding = Column(Vector(VECTOR_SIZE))

    
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
    
    versions = relationship("InstanceVersion", back_populates="instance")
    


class InstanceVersion(Base):
    __tablename__ = "instance_version"
  
    id = Column(Integer, primary_key=True)
    resource_id = Column(String, ForeignKey('resources.id'))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user = Column(String, ForeignKey('users.id'))
    data = Column(JSONB)
    embedding = Column(Vector(VECTOR_SIZE))
    
    instance = relationship("Instances", back_populates="versions")

 
class Work(Base):
    __tablename__ = "works"

    id = Column(String, primary_key=True)
    uri = Column(String, unique=True)
    admin_metadata = Column(Integer, ForeignKey("AdminMetadata.id"))

    group = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    data = Column(JSONB)
    embedding = Column(Vector(VECTOR_SIZE))  
        
    instances = relationship(
       "Instances",
       back_populates="work",
       order_by="Instance.id",
       lazy="joined"
    )
    versions = relationship("WorkVersion", back_populates="work")
    

class WorkVersion(Base):
    __tablename__ = "work_versions"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    admin_metadata = Column(Integer, ForeignKey('AdminMetadataVersion.id'))
    user = Column(String, ForeignKey('users.id'))
    data = Column(JSONB)
    embedding = Column(Vector(VECTOR_SIZE))
    
    work = relationship("Work", back_populates="versions")
