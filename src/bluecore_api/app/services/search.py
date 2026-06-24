"""
Search logic: string parsing, full-text queries, result grouping, and pagination.
The HTTP handlers that call into this live in "app/routes/search.py".
"""

import os
import re
from dataclasses import dataclass
from typing import TypedDict
from urllib.parse import urlencode

from sqlalchemy import func, select, Select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import noload, Session

from bluecore_models.models import Instance, OtherResource, ResourceBase, Work

from bluecore_api.constants import SearchType
from bluecore_api.app.utils.serialize.html import (
    OTHER_SECTION_ORDER,
    resource_section,
    resource_title,
)

BLUECORE_URL: str = os.environ.get("BLUECORE_URL", "https://bcld.info/")


class ResultItem(TypedDict):
    uri: str
    title: str


class ResultGroup(TypedDict):
    label: str
    results: list[ResultItem]


class Pagination(TypedDict):
    start: int
    end: int
    total: int
    prev_url: str | None
    next_url: str | None


class Panel(TypedDict):
    key: str
    title: str | None
    groups: list[ResultGroup]
    total: int
    too_broad: bool
    pagination: Pagination


@dataclass(frozen=True)
class PanelBuildSpec:
    key: str
    title: str | None
    scope_type: SearchType
    offset_param: str
    offset: int
    sibling_offsets: dict[str, int]


def apply_search_timeout(db: Session) -> None:
    """Bound the runtime of the search queries for the current transaction."""
    db.execute(text("SET LOCAL statement_timeout = 20000"))


SPACE_CONDENSER = re.compile(r"\s+")
PHRASE_MAPPER = re.compile(r'"([^"]+)"')
OR_MAPPER = re.compile(r"\s*\|\s*")
COLLON_MAPPER = re.compile(r"\s*:\s*")
INVALID_WILDCARD_MAPPER = re.compile(r"(\*\s*)+")
PHRASE_LEADING_WILDCARD_MAPPER = re.compile(r"^(\*(__PH__)*)+")
TRAILING_OPERATOR_MAPPER = re.compile(r"\s*(&|\|)\s*$")
BARE_AMPERSAND_MAPPER = re.compile(r"(?<!\\)&")


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
    formatted = SPACE_CONDENSER.sub(" ", BARE_AMPERSAND_MAPPER.sub(" ", formatted))
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


def base_select(type: SearchType) -> Select:
    """Unfiltered (by text) base query for a single search scope."""
    if type == SearchType.OTHER_RESOURCES:
        return select(OtherResource).where(OtherResource.is_profile.is_(False))
    return select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))


def run_scope_search(
    db: Session,
    base_stmt: Select,
    formatted: str,
    offset: int,
    limit: int,
) -> tuple[list[ResourceBase], int, bool]:
    """Run one full-text search scope (ranked, with an exact total) on its own page.

    The page and total come back in a single scan via "count(*) OVER ()". The
    query runs under "statement_timeout"; if it is cancelled for running too long
    the scope degrades to empty results flagged as "too_broad" rather than
    failing the whole request, so in an "all" search one scope timing out doesn't
    sink the other.

    Returns "(results, total, too_broad)".
    """
    lang = "simple" if "<->" in formatted else "english"
    search_query = func.to_tsquery(lang, func.unaccent(formatted))
    stmt = base_stmt.where(search_query.op("@@")(ResourceBase.data_vector)).order_by(
        func.ts_rank(ResourceBase.data_vector, search_query).desc(),
        # Stable tiebreaker: broad/wildcard queries produce many rows with the same
        # ts_rank, and without a unique secondary sort Postgres orders ties
        # arbitrarily (varies per run/parallel workers). That makes results reshuffle
        # on refresh and pages overlap/skip. id gives a deterministic total order.
        ResourceBase.id.asc(),
    )
    try:
        apply_search_timeout(db)
        rows = db.execute(
            stmt.add_columns(func.count().over().label("total"))
            .offset(offset)
            .limit(limit)
        ).all()
    except OperationalError:
        db.rollback()
        return [], 0, True
    results = [row[0] for row in rows]
    # An out-of-range page returns no rows (and so no window count); the first and
    # most common page always carries the total.
    total = rows[0][-1] if rows else 0
    return results, total, False


def group_results(results: list[ResourceBase]) -> list[ResultGroup]:
    """Group a result list under labeled headings, preserving rank order.

    Works and Instances each get their own group; OtherResources are bucketed into
    their derived sections (Name Authorities, Subjects, Hubs, ...) in display order.
    Anything else falls into a generic group so results are never silently dropped.
    """

    def item(resource: ResourceBase) -> ResultItem:
        return {"uri": resource.uri, "title": resource_title(resource)}

    groups: list[ResultGroup] = []
    works = [item(r) for r in results if isinstance(r, Work)]
    instances = [item(r) for r in results if isinstance(r, Instance)]
    if works:
        groups.append({"label": "Works", "results": works})
    if instances:
        groups.append({"label": "Instances", "results": instances})

    sections: dict[str, list[ResultItem]] = {}
    for r in results:
        if isinstance(r, OtherResource):
            sections.setdefault(resource_section(r), []).append(item(r))
    ordered = [s for s in OTHER_SECTION_ORDER if s in sections] + sorted(
        s for s in sections if s not in OTHER_SECTION_ORDER
    )
    groups.extend({"label": s, "results": sections[s]} for s in ordered)

    leftover = [
        item(r) for r in results if not isinstance(r, (Work, Instance, OtherResource))
    ]
    if leftover:
        groups.append({"label": "Results", "results": leftover})
    return groups


# Display order for pagination query params
PAGINATION_PARAM_ORDER = (
    "q",
    "type",
    "limit",
    "offset",
    "primary_offset",
    "secondary_offset",
)


def order_query_params(params: dict[str, object]) -> list[tuple[str, object]]:
    """Order params by PAGINATION_PARAM_ORDER for stable, grouped pagination URLs."""

    def rank(key: str) -> int:
        if key in PAGINATION_PARAM_ORDER:
            return PAGINATION_PARAM_ORDER.index(key)
        return len(PAGINATION_PARAM_ORDER)

    return sorted(params.items(), key=lambda kv: (rank(kv[0]), kv[0]))


def build_pagination(
    base_url: str,
    fixed_params: dict[str, object],
    offset_param: str,
    offset: int,
    limit: int,
    total: int,
    count: int,
) -> Pagination:
    """Pagination metadata + prev/next URLs for a single results panel.

    "offset_param" is the query param this panel pages on (e.g. "primary_offset");
    "fixed_params" carries everything to preserve across pages, crucially the
    *other* panel's current offset, so each panel pages independently.
    """

    def url(new_offset: int) -> str:
        params = {**fixed_params, offset_param: new_offset}
        return f"{base_url}?{urlencode(order_query_params(params))}"

    return {
        "start": offset + 1 if count else 0,
        "end": offset + count,
        "total": total,
        "prev_url": url(max(offset - limit, 0)) if offset > 0 else None,
        "next_url": url(offset + limit) if offset + count < total else None,
    }


def build_panel(
    db: Session,
    base_url: str,
    common: dict[str, object],
    formatted: str,
    limit: int,
    spec: PanelBuildSpec,
) -> Panel:
    """Run one scope's search and assemble its render-ready panel.

    "spec.key" is the panel's stable id (used as the DOM id and by the
    partial-update JS); "spec.sibling_offsets" carries the other panels' offsets
    so each panel pages independently without disturbing the others.
    """
    results, total, too_broad = run_scope_search(
        db, base_select(spec.scope_type), formatted, spec.offset, limit
    )
    return {
        "key": spec.key,
        "title": spec.title,
        "groups": group_results(results),
        "total": total,
        "too_broad": too_broad,
        "pagination": build_pagination(
            base_url,
            {**common, **spec.sibling_offsets},
            spec.offset_param,
            spec.offset,
            limit,
            total,
            len(results),
        ),
    }
