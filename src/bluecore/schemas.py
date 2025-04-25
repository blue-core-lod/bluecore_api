from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Dict, List, Optional, Union


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
    data: Optional[str] = None
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


class BatchCreateSchema(BaseModel):
    uri: Optional[str] = None


class BatchSchema(BaseModel):
    uri: Optional[str] = None
    workflow_id: str


class ActivityStreamsEntryPointSchema(BaseModel):
    # populate_by_name is getting deprecated in pydantic v2.11
    #   and will be removed in v3.0.0
    # When upgrading pydantic, change this to
    #   model_config = ConfigDict(validate_by_alias=True, validate_by_name=False)
    model_config = ConfigDict(populate_by_name=True)

    context: Annotated[List[str], Field(alias="@context")]
    summary: str
    type: str
    id: str
    url: Optional[str] = None
    first: Dict[str, str]
    last: Dict[str, str]
    totalItems: int


class ActivityStreamsObjectSchema(BaseModel):
    type: Optional[str] = None
    updated: Optional[str] = None
    id: str


class ActivityStreamsEntityChangeActivitiesSchema(BaseModel):
    summary: str
    published: str
    type: str
    partOf: Optional[str] = None
    object: ActivityStreamsObjectSchema


class ActivityStreamsChangeSetSchema(BaseModel):
    # populate_by_name is getting deprecated in pydantic v2.11
    #   and will be removed in v3.0.0
    # When upgrading pydantic, change this to
    #   model_config = ConfigDict(validate_by_alias=True, validate_by_name=False)
    model_config = ConfigDict(populate_by_name=True)

    context: Annotated[List[Union[str, Dict[str, str]]], Field(alias="@context")]
    type: str
    id: str
    partOf: str
    totalItems: Optional[int] = None
    prev: Optional[str] = None
    next: Optional[str] = None
    orderedItems: List[ActivityStreamsEntityChangeActivitiesSchema]
