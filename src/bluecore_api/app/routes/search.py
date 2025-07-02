# ==============================================================================
# Search across resource types with proper use of JSONB indexes.
# Supports RDF fields, mapped keys for @> optimization,
# and dynamic top-level keys auto-normalized to keys/values.
# ------------------------------------------------------------------------------
from bluecore_api.database import get_db
from bluecore_api.schemas.schemas import ResourceBaseSchema
from bluecore_models.models import Instance, ResourceBase, Work
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List
from bluecore_api.utils.print_output import print_results
from json import dumps

endpoints = APIRouter()

TOP_LEVEL_KEYS = {"dimensions", "code", "status"}
MAPPED_KEYS = {
    "mainTitle": ["title", "mainTitle"],
    "subtitle": ["title", "subtitle"],
    "nonSortNum": ["title", "bflc:nonSortNum"],
    "extent": ["extent", "http://www.w3.org/2000/01/rdf-schema#label"],
    "context_bflc": ["@context", "bflc"],
    "context_mads": ["@context", "mads"],
    "context_vocab": ["@context", "@vocab"],
}


@endpoints.get(
    "/search/",
    response_model=List[ResourceBaseSchema],
)
async def search(
    request: Request,
    db: Session = Depends(get_db),
    type: str = Query(
        default="all",
        description="Resource type: works, instances, or all",
        min_length=1,
        max_length=15,
    ),
    uuid: str = Query(
        default=None,
        min_length=1,
        max_length=500,
        description="Match native UUID column",
    ),
    rdf_id: str = Query(
        default=None, min_length=1, max_length=150, description="RDF ID"
    ),
    rdf_type: str = Query(
        default=None, min_length=1, max_length=50, description="RDF @type"
    ),
    mainTitle: str = Query(
        default=None, min_length=1, max_length=300, description="Exact title"
    ),
    derivedFrom: str = Query(
        default=None,
        min_length=1,
        max_length=300,
        description="Derived from URI (e.g., http://id.loc.gov/resources/instances/11204120)",
    ),
    uri: str = Query(default=None, description="Match native URI column"),
    keys: List[str] = Query(default=[], alias="key", description="Dynamic keys"),
    values: List[str] = Query(default=[], alias="value", description="Dynamic values"),
):
    if type == "works":
        model = Work
        type_filter = "works"
    elif type == "instances":
        model = Instance
        type_filter = "instances"
    elif type == "all":
        model = ResourceBase
        type_filter = None
    else:
        raise HTTPException(status_code=400, detail="Invalid type specified")

    query = db.query(model)
    conditions = []
    params = {}

    # Use BTREE index for native uuid column
    if uuid:
        uuid = uuid.strip().strip('"').strip("'")
        conditions.append("uuid = :uuid")
        params["uuid"] = uuid

    # Use BTREE index for native uri column
    if uri:
        conditions.append("uri = :uri")
        params["uri"] = uri

    # Use BTREE index for native uri column
    if derivedFrom:
        derivedFrom = derivedFrom.strip().strip('"').strip("'")
        conditions.append("(data -> 'derivedFrom' ->> '@id') = :derivedFrom")
        params["derivedFrom"] = derivedFrom

    if rdf_id:
        rdf_id = rdf_id.strip().strip('"').strip("'")
        conditions.append("(data ->> '@id') = :rdf_id")
        params["rdf_id"] = rdf_id

    if rdf_type:
        escaped = rdf_type.strip().strip('"').strip("'")
        jp = f"""jsonb_path_exists(data, '$.**."@type"[*] ? (@ == "{escaped}")')"""
        conditions.append(jp)

    # Use BTREE index for mainTitle (scalar JSONB index)
    if mainTitle:
        mainTitle = mainTitle.strip().strip('"').strip("'")
        conditions.append("(data -> 'title' ->> 'mainTitle') = :mainTitle")
        params["mainTitle"] = mainTitle

    # Add type filter if needed
    if type_filter:
        conditions.append("type = :type_filter")
        params["type_filter"] = type_filter
    else:
        conditions.append("type IN ('works', 'instances')")

    # --- Normalize known top-level keys to dynamic keys ---
    for top_key in TOP_LEVEL_KEYS:
        if top_key in request.query_params and top_key not in keys:
            keys.append(top_key)
            values.append(request.query_params[top_key])

    # --- detect leftover query params ---
    # Any query param NOT in known fields gets added as a dynamic JSONPath
    known_param_names = {
        "type",
        "rdf_id",
        "rdf_type",
        "mainTitle",
        "derivedFrom",
        "uuid",
        "uri",
        "key",
        "value",
    }.union(TOP_LEVEL_KEYS)

    for k, v in request.query_params.items():
        if k not in known_param_names:
            keys.append(k)
            values.append(v)

    # --- Dynamic JSONPath ---
    if keys and values:
        if len(keys) != len(values):
            raise HTTPException(
                status_code=400, detail="Keys and values must match in count."
            )

        for i in range(len(keys)):
            k = keys[i]
            v = values[i].strip().strip('"').strip("'")

            if k in MAPPED_KEYS:
                mapped = MAPPED_KEYS[k]
                json_conditions = {mapped[0]: {mapped[1]: v}}
                conditions.append("data @> :json_condition")
                params["json_condition"] = dumps(json_conditions)
            else:
                escaped_k = k.replace('"', '"')
                escaped_v = v.replace('"', '"').replace("'", "''")
                jp_dynamic = f"""jsonb_path_exists(data, '$.**.{escaped_k} ? (@ == "{escaped_v}")')"""
                conditions.append(jp_dynamic)

    if conditions:
        query = query.filter(text(" AND ".join(conditions)).params(**params))

    # query_results = query.limit(50).all()
    query_results = query.all()

    print_results(query_results, request.url, query, params)

    return query_results
