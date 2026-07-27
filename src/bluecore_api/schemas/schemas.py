from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bluecore_api.constants import BluecoreType


class ErrorResponse(BaseModel):
    title: str
    details: str | None = None
    status: str


class ResourceBaseSchema(BaseModel):
    id: int | None
    type: str
    data: dict[str, Any]
    uri: str | None
    uuid: UUID | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class InstanceCreateSchema(BaseModel):
    work_id: int | None = None
    data: str


class InstanceEmbeddingSchema(BaseModel):
    instance_id: int
    instance_uri: str
    version_id: int
    embedding: list


class InstanceSchema(ResourceBaseSchema):
    type: str = BluecoreType.INSTANCES
    work_id: int | None
    is_expanded: bool = False


class InstanceUpdateSchema(BaseModel):
    data: str | None = None
    work_id: int | None = None


class OtherResourceSchema(BaseModel):
    id: int
    data: dict[str, Any] | list[Any]
    uri: str | None = None


class OtherResourceCreateSchema(BaseModel):
    data: str
    uri: str | None = None


class OtherResourceUpdateSchema(BaseModel):
    data: str | None = None
    uri: str | None = None


class ProfileSchema(BaseModel):
    id: int
    uuid: UUID | None = None
    uri: str | None = None
    data: dict[str, Any] | list[Any]

    model_config = ConfigDict(from_attributes=True)


class ProfileCreateSchema(BaseModel):
    data: str


class ProfileUpdateSchema(BaseModel):
    data: str | None = None


class HubCreateSchema(BaseModel):
    data: str


class HubEmbeddingSchema(BaseModel):
    hub_id: int
    hub_uri: str
    version_id: int
    embedding: list


class HubSchema(ResourceBaseSchema):
    type: str = BluecoreType.HUBS
    is_expanded: bool = False


class HubUpdateSchema(BaseModel):
    data: str | None = None
    hub_id: int | None = None


class WorkCreateSchema(BaseModel):
    hub_id: int | None = None
    data: str


class WorkUpdateSchema(BaseModel):
    data: str | None = None


class WorkSchema(ResourceBaseSchema):
    type: str = BluecoreType.WORKS
    hub_id: int | None
    is_expanded: bool = False


class WorkEmbeddingSchema(BaseModel):
    work_id: int
    work_uri: str
    version_id: int
    embedding: list


class BatchCreateSchema(BaseModel):
    uri: str | None = None


class BatchSchema(BaseModel):
    uri: str | None = None
    workflow_id: str


class LinksSchema(BaseModel):
    first: str
    prev: str | None = None
    next: str | None = None


class SearchResultSchema(BaseModel):
    results: Sequence[ResourceBaseSchema]
    links: LinksSchema
    total: int


class SearchProfileResultSchema(BaseModel):
    results: Sequence[ProfileSchema]
    links: LinksSchema
    total: int


class ExportSchema(BaseModel):
    instance_uri: str


class ExportResponseSchema(BaseModel):
    instance_uri: str
    workflow_id: str
