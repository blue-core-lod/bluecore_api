"""
# ==============================================================================
# Search across resource types with proper use of JSONB indexes.
# Supports RDF fields, mapped keys for @> optimization,
# and dynamic top-level keys auto-normalized to keys/values.
# ------------------------------------------------------------------------------
"""

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


# @endpoints.get("/search/", response_model=List[ResourceBaseSchema])
# async def search(
#     request: Request,
#     db: Session = Depends(get_db),
#     search_params: SearchParams = Depends(),
# ):
#     """
#     #
#         # Search the database for resources by type and optional filters.
#         # --------------------------------------------------------------------------
#         # This endpoint allows searching across different resource types
#         # (works, instances, or all). You can filter results by UUID, RDF ID, RDF type,
#         # main title, derivedFrom, and URI fields. All query parameters are optional,
#         # allowing broad or very specific searches.
#         # --------------------------------------------------------------------------
#         # Example:
#         # /search/?type=instances&mainTitle=Example
#     #
#     """
#     if search_params.resource_type == "works":
#         model = Work
#     elif search_params.resource_type == "instances":
#         model = Instance
#     elif search_params.resource_type == "all":
#         model = ResourceBase
#         search_params.resource_type = None
#     else:
#         raise HTTPException(status_code=400, detail="Invalid type specified")
#
#     query = db.query(model)
#
#     """
#     ##############################
#     ##  SEARCH BUILDER SERVICE  ##
#     ##############################
#     Build WHERE conditions and parameters dynamically
#     """
#     conditions, params = build_search_query(request, search_params)
#
#     if conditions:
#         query = query.filter(*conditions).params(**params)
#
#     query_results = query.all()
#
#     #######################################
#     ##  EXPLAIN ANALYZE SQL PERFORMANCE  ##
#     #######################################
#     compiled_sql = str(query.statement.compile())  # ← no literal_binds!
#     explain_sql = f"EXPLAIN ANALYZE {compiled_sql}"
#     explain_result = db.execute(text(explain_sql), params)
#     explain_output = [row[0] for row in explain_result]
#
#     print_results(
#         query_results, request.url, query, params, search_params, explain_output
#     )
#     return query_results
