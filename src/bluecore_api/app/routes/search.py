from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from bluecore_models.models import OtherResource, ResourceBase

from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH, SearchType
from bluecore_api.schemas.schemas import (
    SearchProfileResultSchema,
    SearchResultSchema,
)
from bluecore_api.app.templating import templates
from bluecore_api.app.services.search import (
    PanelBuildSpec,
    Panel,
    apply_search_timeout,
    base_select,
    build_panel,
    create_count_query,
    format_query,
    generate_links,
)

endpoints = APIRouter()


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
    Search for Works and Instances.
    It transforms the query string to be compatible with PostgreSQL full-text search.
    It supports phrase search using double quotes.
    If the query contains a phrase in double quotes, it will use "simple" language for
        the full-text search to preserve the order of the words in the phrase.
        Stop words will not be ignored and stemming will not be applied in this mode.
    Otherwise, it will use "english" language for the full-text search.
    """
    stmt = base_select(type)
    formatted = format_query(q)
    if formatted:
        lang: str = "simple" if "<->" in formatted else "english"
        search_query = func.to_tsquery(lang, func.unaccent(formatted))
        stmt = stmt.where(
            search_query.op("@@")(ResourceBase.data_vector)
        ).order_by(
            func.ts_rank(ResourceBase.data_vector, search_query).desc(),
            ResourceBase.id.asc(),  # => tiebreaker so equal-ranked rows order deterministically
        )
        params: dict[str, str] = {"q": q, "type": type}
        links_query = f"&{urlencode(params)}"
    else:
        links_query = f"&type={type}"
    try:
        apply_search_timeout(db)
        count_query = create_count_query(stmt)
        total = db.scalar(count_query)
        stmt = stmt.offset(offset).limit(limit)
        results = db.execute(stmt).scalars().all()
    except OperationalError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="Search too broad to complete. Please use a more specific query.",
        )
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
    primary_offset: int = 0,
    secondary_offset: int = 0,
    q: str = "",
    type: SearchType = SearchType.ALL,
    partial: str = "",
) -> HTMLResponse:
    """Public, HTML search for BIBFRAME Works, Instances, OtherResources.

    Backs the header search box (the form posts here, distinct from the JSON
    "GET /search/") and renders "search_results.html".

    An "all" search runs two independent, separately-paginated searches: a primary
    one for Works/Instances (paged via "primary_offset") and a secondary one for
    OtherResources (authorities, agents, subjects, etc) (paged via
    "secondary_offset"). Splitting them avoids the expensive combined "OR" query
    and lets each list page on its own.

    "partial" (a panel "key") is set by the per-panel pagination JS to re-render
    just that one panel as an HTML fragment, so paging one list swaps in place
    without reloading the page or re-running the other panel's query.
    """
    formatted = format_query(q)
    # root_path-aware route URL so pagination links resolve behind the reverse
    # proxy (e.g. /api/search) and when the API is served standalone at the root.
    base = str(request.url_for("search_html"))
    common: dict[str, object] = {"q": q, "type": str(type), "limit": limit}

    if type == SearchType.ALL:
        specs = [
            PanelBuildSpec(
                key="primary",
                title="Works & Instances",
                scope_type=SearchType.ALL,
                offset_param="primary_offset",
                offset=primary_offset,
                sibling_offsets={"secondary_offset": secondary_offset},
            ),
            PanelBuildSpec(
                key="secondary",
                title="Other Resources",
                scope_type=SearchType.OTHER_RESOURCES,
                offset_param="secondary_offset",
                offset=secondary_offset,
                sibling_offsets={"primary_offset": primary_offset},
            ),
        ]
    else:
        specs = [
            PanelBuildSpec(
                key="single",
                title=None,
                scope_type=type,
                offset_param="offset",
                offset=offset,
                sibling_offsets={},
            )
        ]

    # A partial request re-renders only the requested panel (and runs only its query).
    if partial:
        specs = [s for s in specs if s.key == partial]

    panels: list[Panel] = (
        [build_panel(db, base, common, formatted, limit, spec) for spec in specs]
        if formatted
        else []
    )

    if partial:
        # Return just the panel fragment.
        return templates.TemplateResponse(
            request,
            "search_panel.html",
            {"panel": panels[0] if panels else None, "search_q": q},
        )

    return templates.TemplateResponse(
        request,
        "search_results.html",
        {
            "search_q": q,
            "search_type": str(type),
            # the initial landing view renders a prompt instead of a "0 results"
            "searched": bool(formatted),
            "panels": panels,
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