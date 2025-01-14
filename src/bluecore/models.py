from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Integer,
    String, 
    DateTime, 
    ForeignKey,
)

from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import(
    declarative_base,
    mapped_column, 
    Mapped,
    relationship
)

from pgvector.sqlalchemy import Vector

VECTOR_SIZE = 768 # Colbert Model

Base = declarative_base()

class BibframeClass(Base):
    __tablename__ = 'bibframe_classes'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    uri: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<BibframeClass {self.name}>'


class ResourceBibframeClass(Base):
    __tablename__ = "resource_bibframe_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    bf_class_id: Mapped[int] = mapped_column(Integer, ForeignKey('bibframe_classes.id'), nullable=False)
    bf_class: Mapped[BibframeClass] = relationship('BibframeClass')
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey('resources.id'), nullable=False)
    resource: Mapped["Resource"] = relationship('Resource')


class Resource(Base):
    __tablename__ = 'resources'

    id: Mapped[int] = mapped_column(primary_key=True)
    uri: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    data: Mapped[bytes] = mapped_column(JSONB, nullable=False)

    versions: Mapped[List["Version"]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f'<Resource {self.uri}>'
    
class Version(Base):
    __tablename__ = 'versions'

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey('resources.id'), nullable=False)
    resource: Mapped[Resource] = relationship('Resource', back_populates='versions')

    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Version {self.id} {self.resource.uri}>'
    

class TripleVectorIndex(Base):
    __tablename__ = 'triple_vector_index'

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey('versions.id'), nullable=False)
    version: Mapped[Resource] = relationship('Version')
    vector: Mapped[Vector] = mapped_column(Vector(VECTOR_SIZE), nullable=False)

    def __repr__(self):
        return f'<TripleVectorIndex {self.version.resource.uri}>'