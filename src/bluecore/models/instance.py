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


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    uri: Mapped[str] = mapped_column(String(2_000), unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    data: Mapped[bytes] = mapped_column(JSONB)

    versions: Mapped[List["InstanceVersion"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan"
    )


class InstanceVersion(Base):
    __tablename__ = "instance_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[str] = mapped_column(String(256))  # Should be future User identification from KeyCloak
    data: Mapped[bytes] = mapped_column(JSONB)

    embeddings: Mapped[List["InstanceEmbedding"]] = relationship(
        back_populates="instance_version",
        cascade="all, delete-orphan"
    )

    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id"))
    instance: Mapped["Instance"] = relationship(back_populates="versions")


class InstanceEmbedding(Base):
    __tablename__ = "instance_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    embedding: Mapped[float] = mapped_column(Vector(VECTOR_SIZE))
    
    instance_version_id = mapped_column(ForeignKey("instance_versions.id"))
    instance_version: Mapped["InstanceVersion"] = relationship(back_populates="embeddings")
