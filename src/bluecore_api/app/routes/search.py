import os
import re
from typing import Any
from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH, SearchType
from bluecore_api.schemas.schemas import (
    SearchProfileResultSchema,
    SearchResultSchema,
)
from bluecore_models.models import OtherResource, ResourceBase
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, Select
from sqlalchemy.orm import noload, Session
from urllib.parse import urlencode

BLUECORE_URL: str = os.environ.get("BLUECORE_URL", "https://bcld.info/")

endpoints = APIRouter()

SPACE_CONDENSER = re.compile(r"\s+")
PHRASE_MAPPER = re.compile(r'"([^"]+)"')
OR_MAPPER = re.compile(r"\s*\|\s*")
COLLON_MAPPER = re.compile(r"\s*:\s*")
INVALID_WILDCARD_MAPPER = re.compile(r"(\*\s*)+")
PHRASE_LEADING_WILDCARD_MAPPER = re.compile(r"^(\*(__PH__)*)+")
TRAILING_OPERATOR_MAPPER = re.compile(r"\s*(&|\|)\s*$")


def format_query(query: str) -> str:
    """
    Format query
        - Remove leading and trailing spaces.
        - Remove invalid wildcards (e.g. "hello * world *" -> "hello world ").
        - Combine consecutive spaces into a single space.
        - Replace spaces inside double quotes with <-> for phrase search.
        - Reserved characters like ':' in the phrase can cause issues with the full-text search parser.
          Currently &, |, : characters inside quotes are escaped. Add more special characters when reported.
        - Leave '|' sequences outside a phrase intact for OR operations.
        - Replace spaces outside a phrase with ' & ' for AND operations.
        - Replace '*' with ':*' for wildcard search.

    Known limitations:
        - The asterisk (*) character cannot be used as literal value of a query string.
    """

    formatted = query.strip()
    if not formatted or formatted == "*":
        return ""

    formatted = TRAILING_OPERATOR_MAPPER.sub("", formatted)
    formatted = INVALID_WILDCARD_MAPPER.sub("* ", formatted).replace(" * ", " ")
    formatted = SPACE_CONDENSER.sub(" ", formatted)
    formatted = PHRASE_MAPPER.sub(
        lambda m: m.group(1)
        .strip()
        .replace("&", "\\&")
        .replace("|", "__OR_ESCAPE__")
        .replace(":", "__COLON_ESCAPE__")
        .replace(" ", "__PH__"),
        formatted,
    )
    formatted = PHRASE_LEADING_WILDCARD_MAPPER.sub("", formatted)
    formatted = (
        OR_MAPPER.sub("__OR__", formatted)
        .replace("__OR_ESCAPE__", "\\|")
        .replace("://", "__PROTOCOL_ESCAPE__")
    )
    return (
        (
            COLLON_MAPPER.sub(" ", formatted)
            .replace("__PROTOCOL_ESCAPE__", "\\://")
            .replace("__COLON_ESCAPE__", "\\:")
        )
        .strip()
        .replace(" ", " & ")
        .replace("__OR__", " | ")
        .replace("__PH__", " <-> ")
        .replace("*", ":*")
    )


def get_types(type: SearchType) -> list[SearchType]:
    """Return a list of types based on the input type."""
    if type == SearchType.ALL:
        return [SearchType.WORKS, SearchType.INSTANCES]
    else:
        # fastapi should throw an error if the type is not recognized SearchType before getting here
        return [type]


def generate_links(
    verb: str, slice_size: int, limit: int, offset: int, query: str = ""
) -> dict[str, str | None]:
    """
    NOTE: Current Paging strategy used by Sinopia
    """
    bluecore_url = BLUECORE_URL.rstrip("/")
    ret: dict[str, str | None] = {
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
def create_count_query(query: Select[tuple[ResourceBase | OtherResource]]):
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
) -> dict[str, Any]:
    """
    Search for Works ans Instances.
    It transforms the query string to be compatible with PostgreSQL full-text search.
    It supports phrase search using double quotes.
    If the query contains a phrase in double quotes, it will use "simple" language for
        the full-text search to preserve the order of the words in the phrase.
        Stop words will not be ignored and stemming will not be applied in this mode.
    Otherwise, it will use "english" language for the full-text search.
    """
    stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))
    formatted = format_query(q)
    if formatted:
        lang: str = "simple" if "<->" in formatted else "english"
        search_query = func.to_tsquery(lang, func.unaccent(formatted))
        stmt = stmt.where(search_query.op("@@")(ResourceBase.data_vector)).order_by(
            func.ts_rank(ResourceBase.data_vector, search_query).desc()
        )
        params: dict[str, str] = {"q": q, "type": type}
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
) -> dict[str, Any]:
    """
    Search for profiles in the resource base.
    """
    stmt = select(OtherResource).where(OtherResource.is_profile.is_(True))

    formatted = format_query(q)
    if formatted:
        stmt = stmt.where(
            func.to_tsquery("english", formatted).op("@@")(OtherResource.data_vector)
        )
        params: dict[str, str] = {"q": q}
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
