from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH, SearchType
from bluecore_api.schemas.schemas import (
    ResourceBaseSchema,
)
from bluecore_models.models import ResourceBase
from fastapi import APIRouter, Depends, Query
from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseParamsFields
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, TypeVar
import re

endpoints = APIRouter()

T = TypeVar("T")
CustomPage = CustomizedPage[
    Page[T],
    UseParamsFields(
        size=Query(
            DEFAULT_SEARCH_PAGE_LENGTH, ge=1, le=100
        ),  # Set default size to 10 with constraints
    ),
]

SPACE_CONDENSER = re.compile(r"\s+")
PHRASE_MAPPER = re.compile(r'"([^"]+)"')


def format_query(query: str) -> str:
    """
    Format query
    Replace multiple spaces with a single space.
    Separate any phrase terms inside double quotes with <-> and strip double quotes.
    Leave ' | ' sequences intact for OR operations.
    Replace any other spaces with ' & ' for AND operations.
    Replace '*' with ':*' for wildcard search.
    """

    formatted = query.strip()
    # Combine consecutive spaces into a single space
    formatted = SPACE_CONDENSER.sub(" ", formatted)
    # Replace spaces in quoted phrases with a placeholder
    formatted = PHRASE_MAPPER.sub(
        lambda m: m.group(1).strip().replace(" ", "__PH__"), formatted
    )
    return (
        formatted.replace(" | ", "__OR__")
        .replace(" ", " & ")
        .replace("__OR__", " | ")
        .replace("__PH__", " <-> ")
        .replace("*", ":*")
    )


def get_types(type: SearchType) -> List[SearchType]:
    """Return a list of types based on the input type."""
    if type == SearchType.ALL:
        return [SearchType.WORKS, SearchType.INSTANCES]
    else:
        # fastapi should throw an error if the type is not recognized SearchType before getting here
        return [type]


@endpoints.get("/search/")
async def search(
    db: Session = Depends(get_db),
    q: str = "",
    size: int = DEFAULT_SEARCH_PAGE_LENGTH,
    type: SearchType = SearchType.ALL,
) -> CustomPage[ResourceBaseSchema]:
    stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))

    # select * from resource_base where type in ('works', 'instances') and data_vector @@ to_tsquery('english', 'Emma');
    q = format_query(q)
    if q:
        stmt = stmt.where(
            func.to_tsquery("english", q).op("@@")(ResourceBase.data_vector)
        )
    stmt.limit(size)

    return paginate(db, stmt)
