"""GET /search/federated -- Blue Core and external BIBFRAME pools, side by side.

Sits under /search/ so BypassKeycloakForGet's existing "/search" prefix makes it
public without a new allow-list entry (keycloak_auth.py:75).

Deliberately a separate endpoint rather than a parameter on GET /search/: that
response is a flat list with no room to say where a row came from, and a client
that copied an external row from it would fetch the external URI expecting a
Blue Core envelope.
"""

import asyncio
import logging
import time
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from bluecore_api.app.routes.search import search_params, search_tsquery
from bluecore_api.app.views.nodes import title_of
from bluecore_api.app.views.templating import templates
from bluecore_api.constants import (
    BLUECORE_URL,
    DEFAULT_SEARCH_PAGE_LENGTH,
    SearchScope,
    SearchType,
)
from bluecore_api.database import get_db
from bluecore_api.derived_from import find_by_derived_from
from bluecore_api.federated import breaker
from bluecore_api.federated.base import (
    FederatedQuery,
    FederatedResult,
    FederatedSearchError,
    SearchSource,
    SourceResults,
)
from bluecore_api.federated.config import source_timeout_seconds
from bluecore_api.federated.http import client_for
from bluecore_api.federated.registry import (
    SourceContext,
    UnknownSourceError,
    resolve_sources,
)
from bluecore_api.federated.sources.bluecore import BlueCoreSource
from bluecore_api.schemas.federated import (
    FederatedLinksSchema,
    FederatedResultSchema,
    FederatedSearchResultSchema,
    FederatedSourceSchema,
    SourceStatus,
)

logger = logging.getLogger(__name__)

endpoints = APIRouter()

SEARCH_PATH = "search/federated"


def _links(
    query: FederatedQuery, page_size: int, has_search_query: bool
) -> FederatedLinksSchema:
    """Paging links for one group.

    limit and offset apply per source, identically: offset=20 means row 21 of
    each source's own list, not global row 21. There is no honest global
    cursor across sources, so the links live in the groups.

    Mirrors generate_links (search.py:186) including its quirk of offering a
    next link on an exactly-full final page -- the editor already copes with
    that, and a second, subtler difference here would be worse than the quirk.
    """
    base = f"{BLUECORE_URL.rstrip('/')}/api/{SEARCH_PATH}"
    params = search_params(query.q, query.type, query.scope, has_search_query)
    suffix = f"&{urlencode(params)}" if params else ""
    links = FederatedLinksSchema(first=f"{base}?limit={query.limit}&offset=0{suffix}")
    if query.offset > 0:
        prev_offset = max(query.offset - query.limit, 0)
        links.prev = f"{base}?limit={query.limit}&offset={prev_offset}{suffix}"
    if page_size >= query.limit:
        next_offset = query.offset + query.limit
        links.next = f"{base}?limit={query.limit}&offset={next_offset}{suffix}"
    return links


def _to_schema(result: FederatedResult) -> FederatedResultSchema:
    return FederatedResultSchema(**vars(result))


async def _run(
    source: SearchSource, query: FederatedQuery, timings: dict[str, int]
) -> SourceResults:
    """Run one source under a hard wall-clock budget, recording how long it took.

    Belt and braces with federated.http's socket timeouts: those bound each
    read, this bounds everything including redirects and parsing, so one slow
    source costs its own group and nothing else.

    Failures propagate to the caller's gather(return_exceptions=True) rather
    than being caught here, so every source fails the same way; the finally
    clause means a source that blew up still reports its elapsed time.
    """
    if breaker.is_open(source.id):
        timings[source.id] = 0
        raise breaker.CircuitOpenError(
            f"{source.label} is not responding and is being skipped for now."
        )

    started = time.monotonic()
    try:
        async with asyncio.timeout(source_timeout_seconds()):
            results = await source.search(query)
    except Exception:
        # Not BaseException: a cancelled request is not the source's fault and
        # must not count against it.
        breaker.record_failure(source.id)
        raise
    else:
        breaker.record_success(source.id)
        return results
    finally:
        timings[source.id] = int((time.monotonic() - started) * 1000)


async def _annotate_already_held(
    db: Session, outcomes: list[SourceResults | BaseException]
) -> None:
    """Fill in local_uri on external hits we already hold a copy of.

    Without this, the first thing federated search does is manufacture
    duplicates: a cataloger sees an LC record, copies it, and Blue Core ends up
    with two resources derived from the same work with no relationship between
    them. Knowing before the copy turns that into the cataloger's choice.

    One indexed query for the whole response. Runs after the fan-out rather
    than alongside it because it shares the request's Session, which is not
    thread-safe.
    """
    external = [
        result
        for outcome in outcomes
        if isinstance(outcome, SourceResults)
        for result in outcome.results
        if result.local_uri is None
    ]
    if not external:
        return

    # Grouped by type because the backing index leads with it: one seekable
    # query per type beats one index-wide scan for everything.
    by_type: dict[str, set[str]] = defaultdict(set)
    for result in external:
        by_type[result.type].add(result.uri)

    held: dict[str, str] = {}
    for resource_type, uris in by_type.items():
        held |= await asyncio.to_thread(
            find_by_derived_from, db, list(uris), resource_type
        )
    for result in external:
        result.local_uri = held.get(result.uri)


def _group(
    source: SearchSource,
    query: FederatedQuery,
    has_search_query: bool,
    outcome: SourceResults | BaseException,
    elapsed_ms: int,
) -> FederatedSourceSchema:
    """Turn one source's outcome into its group.

    Error text is written for a cataloger, not copied from an exception: it
    ends up in a tab header. A source that failed must never be reported the
    same way as a source that matched nothing -- that is how a timeout becomes
    a hand-catalogued duplicate.
    """
    if isinstance(outcome, SourceResults):
        return FederatedSourceSchema(
            id=source.id,
            label=source.label,
            status=SourceStatus.OK,
            total=outcome.total,
            total_is_exact=outcome.total_is_exact,
            elapsed_ms=elapsed_ms,
            truncated=outcome.truncated,
            note=outcome.note,
            links=_links(query, len(outcome.results), has_search_query),
            results=[_to_schema(r) for r in outcome.results],
        )

    if isinstance(outcome, breaker.CircuitOpenError):
        # Not an error this time round -- we chose not to ask.
        return FederatedSourceSchema(
            id=source.id,
            label=source.label,
            status=SourceStatus.UNAVAILABLE,
            error=str(outcome),
            elapsed_ms=elapsed_ms,
        )

    if isinstance(outcome, TimeoutError):
        status = SourceStatus.TIMEOUT
        error = f"{source.label} did not respond within {source_timeout_seconds():g}s."
    elif isinstance(outcome, FederatedSearchError):
        status = SourceStatus.ERROR
        error = str(outcome)
    else:
        status = SourceStatus.ERROR
        error = f"{source.label} could not be searched."

    # Not logger.exception: this runs outside the except block, on an outcome
    # gather() handed back rather than raised.
    logger.error(
        "Federated source %s failed after %sms",
        source.id,
        elapsed_ms,
        exc_info=outcome,
    )
    return FederatedSourceSchema(
        id=source.id,
        label=source.label,
        status=status,
        error=error,
        elapsed_ms=elapsed_ms,
    )


def _unsupported(source: SearchSource, query: FederatedQuery) -> FederatedSourceSchema:
    """A source that cannot serve the requested type still gets a group.

    Dropping it would leave the cataloger unable to tell "this pool has no
    hubs" from "this pool was not asked".
    """
    return FederatedSourceSchema(
        id=source.id,
        label=source.label,
        status=SourceStatus.UNSUPPORTED,
        elapsed_ms=0,
        note=f"{source.label} cannot be searched for {query.type}.",
    )


def wants_html(request: Request) -> bool:
    """Follows the codebase's negotiation idiom: an explicit Accept: text/html
    gets the human page (app/utils/serializer.py:50)."""
    for raw in request.headers.get("accept", "").split(","):
        media_type = raw.split(";")[0].strip()
        if media_type == "text/html":
            return True
        if media_type in ("application/json", "application/ld+json"):
            return False
    return False


def _html(
    request: Request, body: FederatedSearchResultSchema, query: FederatedQuery
) -> HTMLResponse:
    """Render the grouped results with the existing search template.

    Worth the handful of lines: it makes the whole feature demonstrable in a
    browser without touching sinopia_editor, so evaluating the idea does not
    have to wait on client work.
    """
    groups = [
        {
            "label": source.label,
            "count": source.total,
            "error": source.error,
            "note": source.note,
            "results": [
                {
                    "uri": result.local_uri or result.uri,
                    "title": title_of(result.data),
                    # Only meaningful for an external hit: a Blue Core result
                    # is trivially already in Blue Core.
                    "already_held": bool(
                        result.local_uri and result.source != BlueCoreSource.id
                    ),
                }
                for result in source.results
            ],
        }
        for source in body.sources
    ]
    return templates.TemplateResponse(
        request,
        "search_results.html",
        {
            # Otherwise the shared header form would throw a cataloger back
            # to the local-only search on their next query.
            "search_action": request.url_for("search_federated").path,
            "search_q": query.q,
            "search_type": str(query.type),
            "search_scope": str(query.scope),
            "total": body.total,
            "groups": groups,
            "results": None,
            "pagination": {
                "start": query.offset + 1 if body.total else 0,
                "end": query.offset + sum(len(s.results) for s in body.sources),
                "total": body.total,
                "prev_url": None,
                "next_url": None,
            },
        },
    )


@endpoints.get(
    "/search/federated",
    response_model=FederatedSearchResultSchema,
    operation_id="search_federated",
)
async def search_federated(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(DEFAULT_SEARCH_PAGE_LENGTH, ge=0, le=100),
    offset: int = Query(0, ge=0),
    q: str = "",
    type: SearchType = SearchType.ALL,
    scope: SearchScope = SearchScope.ALL,
    sources: str | None = Query(
        None,
        description=(
            "Comma-separated source ids to query. May only narrow the "
            "configured set, never add to it."
        ),
    ),
) -> Response:
    """Search Blue Core and external BIBFRAME sources at once.

    Results are grouped by source rather than merged into one ranked list: the
    sources score relevance on unrelated scales, and a merged order would bury
    Blue Core's own records under a pool hundreds of times larger -- exactly
    the records a cataloger needs to see in order not to duplicate them.

    Returns 200 whenever any source answered, with `partial` set if some did
    not, so a failing source degrades the page instead of the request.
    """
    query = FederatedQuery(q=q, type=type, scope=scope, limit=limit, offset=offset)
    has_search_query = search_tsquery(q) is not None

    async with client_for(request.app) as http:
        ctx = SourceContext(db=db, http=http)
        try:
            chosen = resolve_sources(ctx, sources)
        except UnknownSourceError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        runnable = [s for s in chosen if type in s.supported_types]
        skipped = [s for s in chosen if type not in s.supported_types]

        timings: dict[str, int] = {}
        outcomes = await asyncio.gather(
            *(_run(source, query, timings) for source in runnable),
            return_exceptions=True,
        )

    await _annotate_already_held(db, list(outcomes))

    groups = [
        _group(source, query, has_search_query, outcome, timings.get(source.id, 0))
        for source, outcome in zip(runnable, outcomes, strict=True)
    ]
    groups.extend(_unsupported(source, query) for source in skipped)
    # Keep the configured order, which _unsupported entries would otherwise break.
    order = {source.id: i for i, source in enumerate(chosen)}
    groups.sort(key=lambda g: order[g.id])

    answered = [g for g in groups if g.status is SourceStatus.OK]
    body = FederatedSearchResultSchema(
        q=q,
        type=str(type),
        scope=str(scope),
        limit=limit,
        offset=offset,
        total=sum(g.total or 0 for g in answered),
        total_is_estimate=any(not g.total_is_exact for g in answered),
        partial=len(answered) < len(groups),
        sources=groups,
    )

    # Every source failing is still worth a full body: the client needs to show
    # which ones died, not a bare error.
    if wants_html(request):
        return _html(request, body, query)

    status_code = 200 if answered or not groups else 502
    return JSONResponse(content=body.model_dump(mode="json"), status_code=status_code)
