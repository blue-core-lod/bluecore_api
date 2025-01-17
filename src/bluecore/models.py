from datetime import datetime

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    DateTime,
    ForeignKey,
)

from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import (
    declarative_base,
    mapped_column,
    Mapped,
    relationship,
)

from pgvector.sqlalchemy import Vector

VECTOR_SIZE = 768  # Colbert Model

Base = declarative_base()


class ResourceBase(Base):
    __tablename__ = "resource_base"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[bytes] = mapped_column(JSONB, nullable=False)
    uri: Mapped[str] = mapped_column(String, nullable=True, unique=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "resource_base",
    }


class Instance(ResourceBase):
    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), primary_key=True
    )
    work_id: Mapped[int] = mapped_column(Integer, ForeignKey("works.id"), nullable=True)
    work: Mapped["Work"] = relationship(
        "Work", foreign_keys=work_id, backref="instances"
    )

    __mapper_args__ = {
        "polymorphic_identity": "instances",
    }

    def __repr__(self):
        return f"<Instance {self.uri}>"


class Work(ResourceBase):
    __tablename__ = "works"
    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), primary_key=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "works",
    }

    def __repr__(self):
        return f"<Work {self.uri}>"


class OtherResource(ResourceBase):
    """
    Stores JSON or JSON-LD resources used to support Work and Instances.
    """

    __tablename__ = "other_resources"
    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), primary_key=True
    )
    is_profile: Mapped[bool] = mapped_column(Boolean, default=False)

    __mapper_args__ = {
        "polymorphic_identity": "other_resources",
    }

    def __repr__(self):
        return f"<OtherResource {self.uri or self.id}>"


class BibframeClass(Base):
    __tablename__ = "bibframe_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    uri: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<BibframeClass {self.name}>"


class ResourceBibframeClass(Base):
    __tablename__ = "resource_bibframe_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    bf_class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bibframe_classes.id"), nullable=False
    )
    bf_class: Mapped[BibframeClass] = relationship("BibframeClass")
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), nullable=False
    )
    resource: Mapped[ResourceBase] = relationship("ResourceBase", backref="classes")

    def __repr__(self):
        return f"<ResourceBibframeClass {self.bf_class.name} for {self.resource.uri}>"


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), nullable=False
    )
    resource: Mapped[ResourceBase] = relationship("ResourceBase", backref="versions")
    data: Mapped[bytes] = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Version at {self.created_at} for {self.resource.uri}>"


class TripleVectorIndex(Base):
    __tablename__ = "triple_vector_index"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("versions.id"), nullable=False
    )
    version: Mapped[Version] = relationship("Version", backref="vector_index")
    vector: Mapped[Vector] = mapped_column(Vector(VECTOR_SIZE), nullable=False)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BibframeOtherResources(Base):
    """
    Creates relationships between Work or Instance and supporting resources
    """

    __tablename__ = "bibframe_other_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    other_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("other_resources.id"), nullable=False
    )
    other_resource: Mapped[OtherResource] = relationship(
        "OtherResource", foreign_keys=other_resource_id
    )
    bibframe_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_base.id"), nullable=False
    )
    bibframe_resource: Mapped[ResourceBase] = relationship(
        "ResourceBase", backref="other_resources"
    )

    created_at = mapped_column(DateTime, default=datetime.utcnow)
    updated_at = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<BibframeOtherResources {self.other_resource.uri or self.other_resource.id} for {self.bibframe_resource.uri}>"
