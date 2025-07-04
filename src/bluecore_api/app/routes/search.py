"""
# ==============================================================================
# Search across resource types with proper use of JSONB indexes.
# Supports RDF fields, mapped keys for @> optimization,
# and dynamic top-level keys auto-normalized to keys/values.
# ------------------------------------------------------------------------------
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List

from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import ResourceBaseSchema
from bluecore_api.schemas.search.schemas import SearchParams
from bluecore_models.models import Instance, ResourceBase, Work
from bluecore_api.app.services.search_builder import build_search_query
from bluecore_api.utils.print_output import print_results

endpoints = APIRouter()


@endpoints.get("/search/", response_model=List[ResourceBaseSchema])
async def search(
    request: Request,
    db: Session = Depends(get_db),
    search_params: SearchParams = Depends(),
):
    """
    #
        # Search the database for resources by type and optional filters.
        # --------------------------------------------------------------------------
        # This endpoint allows searching across different resource types
        # (works, instances, or all). You can filter results by UUID, RDF ID, RDF type,
        # main title, derivedFrom, and URI fields. All query parameters are optional,
        # allowing broad or very specific searches.
        # --------------------------------------------------------------------------
        # Example:
        # /search/?type=instances&mainTitle=Example
    #
    """
    if search_params.resource_type == "works":
        model = Work
    elif search_params.resource_type == "instances":
        model = Instance
    elif search_params.resource_type == "all":
        model = ResourceBase
        search_params.resource_type = None
    else:
        raise HTTPException(status_code=400, detail="Invalid type specified")

    query = db.query(model)

    """
    ############################## 
    ##  SEARCH BUILDER SERVICE  ##
    ############################## 
    Build WHERE conditions and parameters dynamically
    """
    conditions, params = build_search_query(request, search_params)

    if conditions:
        query = query.filter(*conditions).params(**params)

    query_results = query.all()

    #######################################
    ##  EXPLAIN ANALYZE SQL PERFORMANCE  ##
    #######################################
    compiled_sql = str(query.statement.compile())  # ← no literal_binds!
    explain_sql = f"EXPLAIN ANALYZE {compiled_sql}"
    explain_result = db.execute(text(explain_sql), params)
    explain_output = [row[0] for row in explain_result]

    print_results(
        query_results, request.url, query, params, search_params, explain_output
    )
    return query_results
