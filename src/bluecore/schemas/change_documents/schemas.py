from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Dict, List, Optional, Union

"""
There are many hard coded values in the schemas.
These should be moved to constants when other parts of the application reference them.
"""

ENTRY_POINT_CONTEXT: List[str] = [
    "https://www.w3.org/ns/activitystreams",
    "https://emm-spec.org/1.0/context.json",
]

CHANGE_SET_CONTEXT: List[Union[str, Dict[str, str]]] = [
    "https://www.w3.org/ns/activitystreams",
    "https://emm-spec.org/1.0/context.json",
    {"bf": "http://id.loc.gov/ontologies/bibframe/"},
]


class EntryPointSchema(BaseModel):
    # populate_by_name is getting deprecated in pydantic v2.11
    #   and will be removed in v3.0.0
    # When upgrading pydantic, change this to
    #   model_config = ConfigDict(validate_by_alias=True, validate_by_name=False)
    model_config = ConfigDict(
        populate_by_name=True,
        revalidate_instances="subclass-instances",
    )

    context: Annotated[List[str], Field(alias="@context")] = ENTRY_POINT_CONTEXT
    summary: str
    type: str = "OrderedCollection"
    id: str
    url: Optional[str] = None
    first: Dict[str, str]
    last: Dict[str, str]
    totalItems: int


class EntityChangeObjectSchema(BaseModel):
    model_config = ConfigDict(
        revalidate_instances="subclass-instances",
    )

    type: Optional[str] = None
    updated: Optional[str] = None
    id: str


class EntityChangeActivitiesSchema(BaseModel):
    model_config = ConfigDict(
        revalidate_instances="subclass-instances",
    )

    summary: str
    published: str
    type: str
    partOf: Optional[str] = None
    object: EntityChangeObjectSchema


class ChangeSetSchema(BaseModel):
    # populate_by_name is getting deprecated in pydantic v2.11
    #   and will be removed in v3.0.0
    # When upgrading pydantic, change this to
    #   model_config = ConfigDict(validate_by_alias=True, validate_by_name=False)
    model_config = ConfigDict(
        populate_by_name=True,
        revalidate_instances="subclass-instances",
    )

    context: Annotated[List[Union[str, Dict[str, str]]], Field(alias="@context")] = (
        CHANGE_SET_CONTEXT
    )
    type: str = "OrderedCollectionPage"
    id: str
    partOf: str
    totalItems: Optional[int] = None
    prev: Optional[str] = None
    next: Optional[str] = None
    orderedItems: List[EntityChangeActivitiesSchema]
