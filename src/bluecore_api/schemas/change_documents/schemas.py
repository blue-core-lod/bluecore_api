from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

"""
There are many hard coded values in the schemas.
These should be moved to constants when other parts of the application reference them.
"""

ENTRY_POINT_CONTEXT: list[str] = [
    "https://www.w3.org/ns/activitystreams",
    "https://emm-spec.org/1.0/context.json",
]

CHANGE_SET_CONTEXT: list[str | dict[str, str]] = [
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

    context: Annotated[list[str], Field(alias="@context")] = ENTRY_POINT_CONTEXT
    summary: str
    type: str = "OrderedCollection"
    id: str
    url: str | None = None
    first: dict[str, str]
    last: dict[str, str]
    totalItems: int


class EntityChangeObjectSchema(BaseModel):
    model_config = ConfigDict(
        revalidate_instances="subclass-instances",
    )

    type: str | None = None
    updated: str | None = None
    id: str


class EntityChangeActivitiesSchema(BaseModel):
    model_config = ConfigDict(
        revalidate_instances="subclass-instances",
    )

    summary: str
    published: str
    type: str
    partOf: str | None = None
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

    context: Annotated[list[str | dict[str, str]], Field(alias="@context")] = (
        CHANGE_SET_CONTEXT
    )
    type: str = "OrderedCollectionPage"
    id: str
    partOf: str
    totalItems: int | None = None
    prev: str | None = None
    next: str | None = None
    orderedItems: list[EntityChangeActivitiesSchema]
