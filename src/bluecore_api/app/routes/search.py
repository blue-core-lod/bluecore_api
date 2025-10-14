import os
import re
from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH, SearchType
from bluecore_api.schemas.schemas import (
    SearchProfileResultSchema,
    SearchResultSchema,
)
from bluecore_models.models import OtherResource, ResourceBase
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Selectable, select
from sqlalchemy.orm import noload, Session
from sqlalchemy import func
from typing import Dict, List
from urllib.parse import urlencode

BLUECORE_URL: str = os.environ.get("BLUECORE_URL", "https://bcld.info/")

endpoints = APIRouter()

SPACE_CONDENSER = re.compile(r"\s+")
PHRASE_MAPPER = re.compile(r'"([^"]+)"')
OR_MAPPER = re.compile(r"\s*\|\s*")


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
    formatted = OR_MAPPER.sub("__OR__", formatted)
    return (
        formatted.replace(" ", " & ")
        .replace(":", " & ")
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


def generate_links(
    verb: str, slice_size: int, limit: int, offset: int, query: str = ""
) -> Dict[str, str | None]:
    """
    NOTE: Current Paging strategy used by Sinopia
    """
    bluecore_url = BLUECORE_URL.rstrip("/")
    ret: Dict[str, str | None] = {
        "first": f"{bluecore_url}/api/{verb}/?limit={limit}&offset=0{query}"
    }
    if offset > 0:
        ret["prev"] = (
            f"{bluecore_url}/api/{verb}/?limit={limit}&offset={max([offset - limit, 0])}{query}"
        )
    if not slice_size < limit:
        ret["next"] = (
            f"{bluecore_url}/api/{verb}/?limit={limit}&offset={limit + offset}{query}"
        )
    return ret


# Borrowed from https://github.com/uriyyo/fastapi-pagination/blob/main/fastapi_pagination/ext/sqlalchemy.py
def create_count_query(query: Selectable) -> Selectable:
    query = query.order_by(None).options(noload("*"))

    return query.with_only_columns(  # type: ignore[union-attr]
        func.count(),
        maintain_column_froms=True,
    )


@endpoints.get(
    "/search/",
    response_model=SearchResultSchema,
    response_model_exclude_none=True,
    operation_id="search",
)
async def search(
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_SEARCH_PAGE_LENGTH, ge=0, le=100),
    offset: int = 0,
    q: str = "",
    type: SearchType = SearchType.ALL,
):
    stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))
    # select * from resource_base where type in ('works', 'instances') and data_vector @@ to_tsquery('english', 'Emma');
    formatted = format_query(q)
    if formatted:
        stmt = stmt.where(
            func.to_tsquery("english", formatted).op("@@")(ResourceBase.data_vector)
        )
        params: Dict[str, str] = {"q": q, "type": type}
        links_query = f"&{urlencode(params)}"
    else:
        links_query = f"&type={type}"
    count_query = create_count_query(stmt)
    total = db.scalar(count_query)
    stmt = stmt.offset(offset).limit(limit)
    results = db.execute(stmt).scalars().all()
    links = generate_links(
        verb="search",
        slice_size=len(results),
        limit=limit,
        offset=offset,
        query=links_query,
    )
    return {
        "results": results,
        "links": links,
        "total": total,
    }


@endpoints.get(
    "/search/profile",
    response_model=SearchProfileResultSchema,
    response_model_exclude_none=True,
    operation_id="search_profile",
)
async def search_profile(
    db: Session = Depends(get_db),
    q: str = "",
    limit: int = Query(DEFAULT_SEARCH_PAGE_LENGTH, ge=0, le=100),
    offset: int = 0,
):
    """
    Search for profiles in the resource base.
    """
    stmt = select(OtherResource).where(OtherResource.is_profile.is_(True))

    formatted = format_query(q)
    if formatted:
        stmt = stmt.where(
            func.to_tsquery("english", formatted).op("@@")(OtherResource.data_vector)
        )
        params: Dict[str, str] = {"q": q}
        links_query = f"&{urlencode(params)}"
    else:
        links_query = ""
    count_query = create_count_query(stmt)
    total = db.scalar(count_query)

    stmt = stmt.offset(offset).limit(limit)
    results = db.execute(stmt).scalars().all()
    links = generate_links(
        verb="search/profile",
        slice_size=len(results),
        limit=limit,
        offset=offset,
        query=links_query,
    )
    return {
        "results": results,
        "links": links,
        "total": total,
    }
