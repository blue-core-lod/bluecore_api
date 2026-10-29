import os
import re
import unicodedata
from typing import Literal
from urllib.parse import urlencode

from bluecore_models.models import (
    Hub,
    Instance,
    OtherResource,
    Profile,
    ResourceBase,
    Work,
)
from bluecore_models.utils.search import normalize_symbols
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import ColumnElement, Select, and_, func, literal, or_, select
from sqlalchemy.orm import Session, noload

from bluecore_api.app.utils.jsonld import with_context
from bluecore_api.app.utils.profile_versions import with_version_uri
from bluecore_api.app.views.search_display import (
    resource_title,
)
from bluecore_api.app.views.templating import templates
from bluecore_api.constants import (
    DEFAULT_SEARCH_PAGE_LENGTH,
    SearchScope,
    SearchType,
)
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import (
    SearchProfileResultSchema,
    SearchResultSchema,
)

BLUECORE_URL: str = os.environ.get("BLUECORE_URL", "https://bcld.info/")

endpoints = APIRouter()

QUOTED_PHRASE = re.compile(r'"([^"]*)"')
# A ':' between two terms, as in "bluecore:bf2:Work", but not the one in "://".
TERM_COLON = re.compile(r":(?!//)")
# A run of text, and whether a '*' wildcard follows it.
WILDCARD_PIECE = re.compile(r"([^*]+)(\*?)")
WORD_CHARACTER = re.compile(r"\w")
# Characters to_tsquery reads as syntax rather than text. '*' is handled as the
# wildcard before anything is escaped, and '"' never reaches to_tsquery.
TSQUERY_SYNTAX = frozenset("&|!()<>:'\\")


def _separate_symbols(text: str) -> str:
    """
    Turn non-ASCII punctuation, symbols and fractions into spaces.

    unaccent runs after format_query, in SQL, and rewrites some of these into
    tsquery syntax: « becomes <<, © becomes (C), ½ becomes " 1/2". A backslash
    can't escape a character that turns into two, so they are dropped instead.
    The text parser discards them when it indexes a document anyway.
    """
    return "".join(
        " " if not ch.isascii() and _is_symbol(unicodedata.category(ch)) else ch
        for ch in text
    )


def _is_symbol(category: str) -> bool:
    """Punctuation, a symbol, or a number that isn't a digit (½, ⑴)."""
    return category[0] in "PS" or category == "No"


def _escape(text: str) -> str:
    """
    Backslash escape text so to_tsquery reads it as a single operand.

    Non-ASCII letters are escaped too: unaccent rewrites a few of them into
    syntax, ʻ into ', and leaves the backslash in front of what it produces.
    Escaping any other letter is harmless.
    """
    return "".join(
        "\\" + ch
        if ch in TSQUERY_SYNTAX
        or not ch.isascii()
        and unicodedata.category(ch).startswith("L")
        else ch
        for ch in text
    )


def _terms(word: str) -> list[str]:
    """
    The tsquery operands for one whitespace-free word.

    A '*' marks the text before it as a prefix ("worl*" -> "worl:*") and splits
    the word there, so "inval*wildcard" is two terms. A piece with no letter or
    digit in it, a bare "&" or "<->", is dropped: the document side holds no
    token for it, so in a phrase it would be a gap the index can never match.
    """
    return [
        _escape(piece) + (":*" if wildcard else "")
        for piece, wildcard in WILDCARD_PIECE.findall(word)
        if WORD_CHARACTER.search(piece)
    ]


def format_query(query: str) -> str:
    """
    Format a user query as to_tsquery input.

    Query syntax:
        - "double quotes" search for a phrase: its terms are joined with <->.
        - '|' outside a phrase is OR.
        - '*' after a term is a prefix search ("worl*" -> "worl:*"). A '*' with
          nothing before it is dropped.
        - ':' outside a phrase separates terms, except in "://".
        - Anything else separated by spaces is ANDed.

    Every other tsquery operator, '&', '!', '(', ')', '<->', is literal text.
    It is escaped when it sits inside a word ("AT&T"), and dropped when it
    stands alone ("fish & chips"), because the document side holds no token
    for it. The result is always valid to_tsquery syntax.

    Known limitations:
        - The asterisk (*) character cannot be used as literal value of a query string.
        - '!' and '(' ')' are not NOT or grouping.
    """

    # Each item is an operand, or None for an OR between two of them.
    items: list[str | None] = []
    for index, segment in enumerate(QUOTED_PHRASE.split(_separate_symbols(query))):
        if index % 2:
            phrase = [term for word in segment.split() for term in _terms(word)]
            if phrase:
                items.append(" <-> ".join(phrase))
            continue
        for position, alternative in enumerate(segment.replace('"', " ").split("|")):
            if position:
                items.append(None)
            items.extend(
                term
                for word in alternative.split()
                for part in TERM_COLON.split(word)
                for term in _terms(part)
            )

    formatted = ""
    pending_or = False
    for item in items:
        if item is None:
            pending_or = bool(formatted)
        else:
            if formatted:
                formatted += " | " if pending_or else " & "
            formatted += item
            pending_or = False
    return formatted


def search_tsquery(q: str):
    """
    Build the tsquery for a raw user query, or None if it is empty.

    normalize_symbols -> format_query -> unaccent -> to_tsquery

    normalize_symbols has to see raw input, before format_query inserts tsquery
    operators. It emits space padded sentinels, and a space introduced after the
    operators are in place would sit between two terms with nothing joining
    them, which to_tsquery rejects.

    unaccent stays on the SQL side.
    """
    formatted = format_query(normalize_symbols(q))
    if not formatted:
        return None
    lang = "simple" if "<->" in formatted else "english"
    return func.to_tsquery(lang, func.unaccent(formatted))


def get_types(type: SearchType) -> list[SearchType]:
    """Return a list of types based on the input type."""
    if type == SearchType.ALL:
        return [SearchType.WORKS, SearchType.INSTANCES, SearchType.HUBS]
    else:
        # fastapi should throw an error if the type is not recognized SearchType before getting here
        return [type]


# (model, heading) in the order the groups appear on the results page. A search
# for a single type only ever matches one of them, so this drives both the "all"
# search's grouping and the one labeled group a single-type search shows.
SEARCH_GROUPS: list[tuple[type[ResourceBase], str]] = [
    (Work, "Works"),
    (Instance, "Instances"),
    (Hub, "Hubs"),
]

# Each scope points directly to its indexed model column. Any future scopes
# only needs another enum value, indexed column, and entry here.
SEARCH_VECTORS = {
    SearchScope.ALL: ResourceBase.data_vector,
    SearchScope.TITLE: ResourceBase.title_vector,
}


def apply_resource_search(
    stmt: Select, q: str, scope: SearchScope
) -> tuple[Select, bool]:
    """Apply the chosen field scope and a stable relevance order to a query.
    The Identifier scope does an exact identifier lookup with the search text.

    The boolean tells callers whether there was search text, so they can build
    links without repeating the matching logic.
    """
    if scope == SearchScope.IDENTIFIER:
        if not q.strip():
            return stmt.order_by(ResourceBase.id), False
        stmt = stmt.where(identifier_match(q))
        return stmt.order_by(ResourceBase.id), True

    search_query = search_tsquery(q)
    if search_query is None:
        return stmt.order_by(ResourceBase.id), False

    search_vector = SEARCH_VECTORS[scope]
    # Break ties on rank with the primary key so equally-ranked results keep a
    # stable, repeatable order across identical searches.
    stmt = stmt.where(search_query.op("@@")(search_vector)).order_by(
        func.ts_rank(search_vector, search_query).desc(),
        ResourceBase.id,
    )
    return stmt, True


# The only identifier schemes that are indexed. A prefix from this list (like
# "isbn:") limits an identifier search to that one scheme.
IDENTIFIER_SCHEMES = ["isbn", "issn", "lccn", "doi"]


def identifier_match(identifier: str) -> ColumnElement[bool]:
    """Build the condition that finds records with the identifier a user typed.
    The text is cleaned up inside the query by the same database function that
    fills the identifiers column, so what a user types lines up with what is stored.

    - "isbn:9780140449112" only matches ISBNs
    - "9780140449112" matches that value as an ISBN, ISSN, LCCN or DOI
    """
    identifier = identifier.strip()
    prefix, colon, value = identifier.partition(":")
    scheme = prefix.strip().lower()

    if colon and scheme in IDENTIFIER_SCHEMES:
        cleaned_values = func.bluecore_identifier_values(scheme, value)
        # Put the scheme back in front of each cleaned value
        # ("isbn:9780140449112"), because only those match this one scheme
        cleaned_value = func.unnest(cleaned_values).column_valued("cleaned_value")
        prefixed_values = select(literal(f"{scheme}:") + cleaned_value)
        # Postgres can't see inside the prefixed values when it plans the query,
        # so it would scan the whole table. Matching the plain values too lets
        # it use the index; the prefixed ones then keep only this scheme.
        return and_(
            ResourceBase.identifiers.overlap(cleaned_values),
            ResourceBase.identifiers.overlap(
                func.array(prefixed_values.scalar_subquery())
            ),
        )

    # No prefix: clean up the text as each scheme would, and match the values
    # that are stored without a scheme
    return or_(
        *(
            ResourceBase.identifiers.overlap(
                func.bluecore_identifier_values(each_scheme, identifier)
            )
            for each_scheme in IDENTIFIER_SCHEMES
        )
    )


def search_params(
    q: str, type: SearchType, scope: SearchScope, has_search_query: bool
) -> dict[str, str]:
    """The parameters a next/prev link needs to repeat the current search.
    Both endpoints build their links here, so the two cannot drift apart.
    """
    params: dict[str, str] = {}
    if has_search_query:
        params["q"] = q
    params["type"] = str(type)
    if scope != SearchScope.ALL:
        params["scope"] = str(scope)
    return params


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
def create_count_query(
    query: Select[tuple[ResourceBase]] | Select[Profile] | Select[tuple[OtherResource]],
):
    query = query.order_by(None).options(noload("*"))

    return query.with_only_columns(
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
    scope: SearchScope = SearchScope.ALL,
) -> dict[str, object]:
    """
    Search for Works, Instances and Hubs.
    With `scope=identifier`, `q` is an exact identifier lookup instead:
        `isbn:9780140449112` searches ISBNs only, `9780140449112` searches ISBNs,
        ISSNs, LCCNs and DOIs. Spaces, hyphens and letter case don't matter.
    It transforms the query string to be compatible with PostgreSQL full-text search.
    It supports phrase search using double quotes.
    If the query contains a phrase in double quotes, it will use "simple" language for
        the full-text search to preserve the order of the words in the phrase.
        Stop words will not be ignored and stemming will not be applied in this mode.
    Otherwise, it will use "english" language for the full-text search.
    """
    stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))
    stmt, has_search_query = apply_resource_search(stmt, q, scope)
    links_query = f"&{urlencode(search_params(q, type, scope, has_search_query))}"
    count_query = create_count_query(stmt)
    total = db.scalar(count_query)
    stmt = stmt.offset(offset).limit(limit)
    results = db.execute(stmt).scalars().all()
    for result in results:
        with_context(result.data)
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


@endpoints.get("/search", response_class=HTMLResponse, include_in_schema=False)
async def search_html(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_SEARCH_PAGE_LENGTH, ge=0, le=100),
    offset: int = 0,
    q: str = "",
    type: SearchType = SearchType.ALL,
    scope: SearchScope = SearchScope.ALL,
) -> HTMLResponse:
    """Public, HTML search for BIBFRAME Works, Instances and Hubs.

    Backs the header search box (the form posts here, distinct from the
    JSON `GET /search/`) and renders the ``search_results.html`` template.
    """
    stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(type)))
    stmt, has_search_query = apply_resource_search(stmt, q, scope)
    total = db.scalar(create_count_query(stmt)) or 0
    results = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    for result in results:
        with_context(result.data)

    def item(resource: ResourceBase) -> dict[str, str]:
        return {
            "uri": resource.uri,
            "title": resource_title(resource),
        }

    # Results are grouped under a labeled heading (see SEARCH_GROUPS). For an
    # "all" search, Works, Instances and Hubs each get their own group; a
    # single-type search shows just that one labeled group.
    groups: list[dict] = []
    for model, label in SEARCH_GROUPS:
        matched = [item(r) for r in results if isinstance(r, model)]
        if matched:
            groups.append({"label": label, "results": matched})

    # Build pagination URLs from the request's root_path-aware route URL so they
    # resolve correctly behind the reverse proxy (e.g. /api/search) and when the
    # API is served standalone at the root.
    base = str(request.url_for("search_html"))

    def page_url(new_offset: int) -> str:
        params: dict[str, str | int] = {
            **search_params(q, type, scope, has_search_query),
            "limit": limit,
            "offset": new_offset,
        }
        return f"{base}?{urlencode(params)}"

    pagination = {
        "start": offset + 1 if total else 0,
        "end": offset + len(results),
        "total": total,
        "prev_url": page_url(max(offset - limit, 0)) if offset > 0 else None,
        "next_url": page_url(offset + limit) if offset + len(results) < total else None,
    }

    return templates.TemplateResponse(
        request,
        "search_results.html",
        {
            "search_q": q,
            "search_type": str(type),
            "search_scope": str(scope),
            "total": total,
            "groups": groups,
            "results": None,
            "pagination": pagination,
        },
    )


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
    nested: Literal["include", "exclude"] = "include",
) -> dict[str, object]:
    """
    Search for profiles in the resource base.
    """
    stmt = select(Profile)
    if nested == "exclude":
        # is_nested is a correlated NOT EXISTS over profile_relations, so this
        # stays one statement and the count and paging below still work. The
        # self-nesting case is a CHECK constraint on that table, so there is
        # nothing to exclude for it here.
        stmt = stmt.where(~Profile.is_nested)

    search_query = search_tsquery(q)
    params: dict[str, str] = {}
    if search_query is not None:
        stmt = stmt.where(search_query.op("@@")(Profile.data_vector))
        params["q"] = q
    if nested == "exclude":
        params["nested"] = nested
    links_query = f"&{urlencode(params)}" if params else ""
    count_query = create_count_query(stmt)
    total = db.scalar(count_query)

    stmt = stmt.offset(offset).limit(limit)
    # One version query per profile, which is fine at a page of profiles.
    results = [with_version_uri(db, profile) for profile in db.execute(stmt).scalars()]
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
