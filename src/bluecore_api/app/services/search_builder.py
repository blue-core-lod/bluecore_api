"""
# ==============================================================================
# Build WHERE conditions for /search
# Combines known top-level fields, mapped nested RDF keys,
# dynamic user-provided JSONPath expressions,
# and takes advantage of Postgres JSONB indexes.
# ------------------------------------------------------------------------------
"""

from sqlalchemy import text
from json import dumps

from bluecore_api.app.config.search_constants import (
    TOP_LEVEL_KEYS,
    MAPPED_KEYS,
    INDEXED_FACETS,
)


def build_search_query(request, search_params):
    conditions = []
    params = {}

    """
    #############################################################
    ##  Direct indexed columns (BTREE) or scalar JSONB fields  ##
    #############################################################
    """
    resource_type = search_params.resource_type
    uuid = search_params.uuid
    rdf_id = search_params.rdf_id
    rdf_type = search_params.rdf_type
    mainTitle = search_params.mainTitle
    derivedFrom = search_params.derivedFrom
    uri = search_params.uri
    keys = search_params.keys or []
    values = search_params.values or []

    if uuid:
        conditions.append(text("uuid = :uuid"))
        params["uuid"] = uuid.strip().strip('"').strip("'")

    if uri:
        conditions.append(text("uri = :uri"))
        params["uri"] = uri.strip().strip('"').strip("'")

    if derivedFrom:
        conditions.append(text("(data -> 'derivedFrom' ->> '@id') = :derivedFrom"))
        params["derivedFrom"] = derivedFrom.strip().strip('"').strip("'")

    if rdf_id:
        conditions.append(text("(data ->> '@id') = :rdf_id"))
        params["rdf_id"] = rdf_id.strip().strip('"').strip("'")

    if rdf_type:
        escaped = rdf_type.strip().strip('"').strip("'")
        conditions.append(
            text(f"""jsonb_path_exists(data, '$.**."@type"[*] ? (@ == "{escaped}")')""")
        )

    if mainTitle:
        conditions.append(text("(data -> 'title' ->> 'mainTitle') = :mainTitle"))
        params["mainTitle"] = mainTitle.strip().strip('"').strip("'")

    if resource_type:
        conditions.append(text("type = :type"))
        params["type"] = resource_type
    else:
        conditions.append(text("type IN ('works', 'instances')"))

    """
    ########################################################
    ##  Normalize known top-level keys into dynamic keys  ##
    ##  Example: ?status=active adds 'status' to keys[]   ##
    ########################################################
    """
    for top_key in TOP_LEVEL_KEYS:
        if top_key in request.query_params and top_key not in keys:
            keys.append(top_key)
            values.append(request.query_params[top_key])

    INDEXED_FACETS.union(TOP_LEVEL_KEYS)

    for k, v in request.query_params.items():
        if k not in INDEXED_FACETS:
            keys.append(k)
            values.append(v)

    """
    ############################################################
    ##  Build JSONB path exists expressions for dynamic keys  ##
    ############################################################
    """
    if keys and values:
        if len(keys) != len(values):
            raise ValueError("Keys and values must match in count")

        for i in range(len(keys)):
            k = keys[i]
            v = values[i].strip().strip('"').strip("'")

            if k in MAPPED_KEYS:
                mapped = MAPPED_KEYS[k]
                json_conditions = {mapped[0]: {mapped[1]: v}}
                conditions.append(text("data @> :json_condition"))
                params["json_condition"] = dumps(json_conditions)
            else:
                escaped_k = k.replace('"', '"')
                escaped_v = v.replace('"', '"').replace("'", "''")
                jp_dynamic = f"""jsonb_path_exists(data, '$.**.{escaped_k} ? (@ == "{escaped_v}")')"""
                conditions.append(text(jp_dynamic))

    return conditions, params
