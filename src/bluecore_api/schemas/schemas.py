from typing import Optional

from pydantic import BaseModel
from datetime import datetime
from bluecore_api.constants import BluecoreType
from typing import Any, Dict
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


class InstanceSchema(ResourceBaseSchema):
    type: str = BluecoreType.INSTANCES
    work_id: Optional[int]


class InstanceUpdateSchema(BaseModel):
    data: Optional[str] = None
    work_id: Optional[int] = None


class OtherResourceSchema(BaseModel):
    data: str
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


class BatchCreateSchema(BaseModel):
    uri: Optional[str] = None


class BatchSchema(BaseModel):
    uri: Optional[str] = None
    workflow_id: str
