"""
# ==============================================================================
# Search across resource types with proper use of JSONB indexes.
# Supports RDF fields, mapped keys for @> optimization,
# dynamic top-level keys auto-normalized to keys/values,
# and prints query performance stats with EXPLAIN ANALYZE.
# ------------------------------------------------------------------------------
"""

from bluecore_api.database import get_db
from bluecore_api.constants import DEFAULT_SEARCH_PAGE_LENGTH
from bluecore_api.schemas.schemas import ResourceBaseSchema
from bluecore_api.app.services.search_builder import build_search_query
from bluecore_api.utils.print_output import print_results
from bluecore_models.models import Instance, ResourceBase, Work
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_pagination import Params, Page
from fastapi_pagination.customization import CustomizedPage, UseParamsFields
from fastapi_pagination.ext.sqlalchemy import paginate

from sqlalchemy.orm import Session
from sqlalchemy import text, select
from typing import TypeVar

from bluecore_api.schemas.search.schemas import SearchParams


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


# ==============================================================================
# Search across resource types with proper use of JSONB indexes.
# Supports RDF fields, mapped keys for @> optimization,
# dynamic top-level keys auto-normalized to keys/values,
# and prints query performance stats with EXPLAIN ANALYZE.
# ------------------------------------------------------------------------------
@endpoints.get("/search/")
async def search(
    request: Request,
    db: Session = Depends(get_db),
    search_params: SearchParams = Depends(),
) -> CustomPage[ResourceBaseSchema]:
    match search_params.resource_type:
        case "works":
            stmt = select(Work)
        case "instances":
            stmt = select(Instance)
        case "all" | None:
            stmt = select(ResourceBase).where(ResourceBase.type != text("'other_resources'"))
        case _:
            raise HTTPException(status_code=400, detail="Invalid type specified")

    #######################
    ##  BUILD SQL QUERY  ##
    #######################
    conditions, sql_params = build_search_query(request, search_params)

    if conditions:
        stmt = stmt.where(*conditions).params(**sql_params)

    #######################################
    ##  EXPLAIN ANALYZE SQL PERFORMANCE  ##
    #######################################
    compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    explain_sql = f"EXPLAIN ANALYZE {compiled_sql}"
    explain_result = db.execute(text(explain_sql), sql_params)
    explain_output = [row[0] for row in explain_result]


    ################
    ##  Paginate  ##
    ################
    page = paginate(db, stmt)

    ####################
    ##  PRINT OUTPUT  ##
    ####################
    print_results(
        page.items,
        str(request.url),
        compiled_sql,
        sql_params,
        search_params,
        explain_output,
        page.total,
        page.page,
        page.size,
        page.pages,
    )

    return page
