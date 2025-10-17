from typing import Optional

from pydantic import BaseModel
from datetime import datetime
from bluecore_api.constants import BluecoreType
from typing import Any, Dict, List, Sequence
from uuid import UUID


class ErrorResponse(BaseModel):
    title: str
    details: Optional[str] = None
    status: str


class ResourceBaseSchema(BaseModel):
    id: Optional[int]
    type: str
    data: Dict[str, Any]
    uri: Optional[str]
    uuid: Optional[UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class InstanceCreateSchema(BaseModel):
    work_id: Optional[int]
    data: str


class InstanceEmbeddingSchema(BaseModel):
    instance_id: int
    instance_uri: str
    version_id: int
    embedding: list


class InstanceSchema(ResourceBaseSchema):
    type: str = BluecoreType.INSTANCES
    work_id: Optional[int]


class InstanceUpdateSchema(BaseModel):
    data: Optional[str] = None
    work_id: Optional[int] = None


class OtherResourceSchema(BaseModel):
    id: int
    data: Dict[str, Any] | List[Any]
    uri: Optional[str] = None
    is_profile: bool


class OtherResourceCreateSchema(BaseModel):
    data: str
    uri: Optional[str] = None
    is_profile: bool = False


class OtherResourceUpdateSchema(BaseModel):
    data: Optional[str] = None
    uri: Optional[str] = None
    is_profile: Optional[bool] = None


class WorkCreateSchema(BaseModel):
    data: str


class WorkUpdateSchema(BaseModel):
    data: Optional[str] = None


class WorkSchema(ResourceBaseSchema):
    type: str = BluecoreType.WORKS


class WorkEmbeddingSchema(BaseModel):
    work_id: int
    work_uri: str
    version_id: int
    embedding: list


class BatchCreateSchema(BaseModel):
    uri: Optional[str] = None


class BatchSchema(BaseModel):
    uri: Optional[str] = None
    workflow_id: str


class LinksSchema(BaseModel):
    first: str
    prev: Optional[str] = None
    next: Optional[str] = None


class SearchResultSchema(BaseModel):
    results: Sequence[ResourceBaseSchema]
    links: LinksSchema
    total: int


class SearchProfileResultSchema(BaseModel):
    results: Sequence[OtherResourceSchema]
    links: LinksSchema
    total: int


class ExportSchema(BaseModel):
    instance_uri: str


class ExportResponseSchema(BaseModel):
    instance_uri: str
    workflow_id: str
