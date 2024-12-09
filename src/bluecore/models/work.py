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
    mapped_column, 
    Mapped,
    relationship
)

from pgvector.sqlalchemy import Vector

from bluecore.app.database import Base, VECTOR_SIZE

class Work(Base):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(primary_key=True)
    uri: Mapped[str] = mapped_column(String(2_000), unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    data: Mapped[bytes] = mapped_column(JSONB)

    versions: Mapped[List["WorkVersion"]] = relationship(
        back_populates="work",
         cascade="all, delete-orphan"
    )
    

class WorkVersion(Base):
    __tablename__ = "work_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped[str] = mapped_column(String(256))  # Should be future User identification from KeyCloak
    data: Mapped[bytes] = mapped_column(JSONB)

    embeddings: Mapped[List["WorkEmbedding"]] = relationship(
        back_populates="work_version",
        cascade="all, delete-orphan"
    )

    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"))
    work: Mapped["Work"] = relationship(back_populates="versions")


class WorkEmbedding(Base):
    __tablename__ = "work_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    embedding: Mapped[float] = mapped_column(Vector(VECTOR_SIZE))
    work_version_id: Mapped[int] = mapped_column(ForeignKey("work_versions.id"))
    work_version: Mapped["WorkVersion"] = relationship(back_populates="embeddings")
