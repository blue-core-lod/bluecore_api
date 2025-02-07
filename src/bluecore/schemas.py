from typing import Optional

from pydantic import BaseModel
from datetime import datetime


class ErrorResponse(BaseModel):
    title: str
    details: Optional[str] = None
    status: str


class ResourceBaseSchema(BaseModel):
    id: Optional[int]
    type: str
    data: str
    uri: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
       from_attributes = True


class InstanceCreateSchema(BaseModel):
    work_id: Optional[int]
    data: str
    uri: Optional[str]


class InstanceSchema(ResourceBaseSchema):
    type: str = "instances"
    work_id: Optional[int]


class InstanceUpdateSchema(BaseModel):
    data: Optional[bytes] = None
    uri: Optional[str] = None
    work_id: Optional[int] = None


class WorkCreateSchema(BaseModel):
    data: str
    uri: Optional[str]


class WorkUpdateSchema(BaseModel):
    data: Optional[str] = None
    uri: Optional[str] = None


class WorkSchema(ResourceBaseSchema):
    type: str = "works"


