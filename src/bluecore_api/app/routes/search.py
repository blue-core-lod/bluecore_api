from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH
from bluecore_api.schemas.schemas import (
    ResourceBaseSchema,
)
from bluecore_models.models import Instance, ResourceBase, Work
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseParamsFields
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import TypeVar

endpoints = APIRouter()

T = TypeVar("T")
CustomPage = CustomizedPage[
    Page[T],
    UseParamsFields(
        size=Query(
            DEFAULT_SEARCH_PAGE_LENGTH, ge=1, le=100
        ),  # Set default size to 100 with constraints
    ),
]


@endpoints.get("/search/")
async def search(
    db: Session = Depends(get_db),
    type: str = "all",
    size: int = DEFAULT_SEARCH_PAGE_LENGTH,
) -> CustomPage[ResourceBaseSchema]:
    match type:
        case "all":
            stmt = (
                select(ResourceBase)
                .where(ResourceBase.type != "other_resources")
                .limit(size)
            )
        case "works":
            stmt = select(Work).limit(size)
        case "instances":
            stmt = select(Instance).limit(size)
        case _:
            raise HTTPException(status_code=400, detail="Invalid type specified")

    return paginate(db, stmt)
