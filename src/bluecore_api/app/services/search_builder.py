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
    keywords = search_params.keywords
    uuid = search_params.uuid
    rdf_id = search_params.rdf_id
    rdf_type = search_params.rdf_type
    mainTitle = search_params.mainTitle
    derivedFrom = search_params.derivedFrom
    uri = search_params.uri
    keys = search_params.keys or []
    values = search_params.values or []

    if resource_type and resource_type not in ("all", None):
        conditions.append(text("type = :type"))
        params["type"] = resource_type

    if keywords:
        conditions, params = _build_sql_for_keywords(keywords, conditions, params)

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
        conditions, params = _build_sql_for_main_title(mainTitle, conditions, params)

    keys, values, conditions, params = _normalize_keys(
        request, keys, values, conditions, params
    )

    if keys and values:
        conditions, params = _build_sql_for_key_value_pairs(
            keys, values, conditions, params
        )

    return conditions, params


"""
################################################################################
###########################  PRIVATE METHODS  ##################################
################################################################################  
"""

"""
########################################################
##  Normalize known top-level keys into dynamic keys  ##
##  Example: ?status=active adds 'status' to keys[]   ##
########################################################
"""


def _normalize_keys(request, keys, values, conditions, params):
    seen_keys = set(keys)

    for top_key in TOP_LEVEL_KEYS:
        if top_key in request.query_params and top_key not in seen_keys:
            keys.append(top_key)
            values.append(request.query_params[top_key])
            seen_keys.add(top_key)

    known_facets = INDEXED_FACETS.union(
        TOP_LEVEL_KEYS
    )

    skip_keys = {"keyword", "page", "size"}

    for k, v in request.query_params.items():
        if k not in known_facets and k not in skip_keys and k not in seen_keys:
            keys.append(k)
            values.append(v)
            seen_keys.add(k)

    return keys, values, conditions, params


"""
#####################################
##  Build SQL for mainTitle query  ##
#####################################
"""


def _build_sql_for_main_title(mainTitle, conditions, params):
    mainTitle_clean = mainTitle.strip()
    if mainTitle_clean.startswith("~"):
        # Use ILIKE for partial match, drop the ~
        stripped = mainTitle_clean[1:].strip().strip('"').strip("'").strip()
        conditions.append(text("(data -> 'title' ->> 'mainTitle') ILIKE :mainTitle"))
        params["mainTitle"] = f"%{stripped}%"
    else:
        # Exact match
        stripped = mainTitle_clean.strip().strip('"').strip("'").strip()
        conditions.append(text("(data -> 'title' ->> 'mainTitle') = :mainTitle"))
        params["mainTitle"] = stripped

    return conditions, params


"""
############################################################
##  Build JSONB path exists expressions for dynamic keys  ##
############################################################
"""


def _build_sql_for_key_value_pairs(keys, values, conditions, params):
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


"""
############################################
##  Build WHERE conditions for keywords.  ##
##   Supports:                            ##
##   - Exact phrases ("text")             ##
##   - Partial word wildcards (word*)     ##
##   - | for OR logic within a keyword    ##
##   - AND for multiple keywords          ##
############################################
"""


def _build_sql_for_keywords(keywords, conditions, params):
    keyword_clauses = []
    for index, keyword in enumerate(keywords):
        keyword_clean = keyword.strip()
        if not keyword_clean:
            continue

        or_parts = keyword_clean.split("|")
        or_conditions = []

        for part in or_parts:
            part = part.strip()
            if not part:
                continue

            param_name = f"kwSet_{index + 1}_val_{len(or_conditions) + 1}"

            if part.startswith('"') and part.endswith('"'):
                # Exact phrase
                phrase = part[1:-1].strip()
                or_conditions.append(f"data::text ILIKE :{param_name}")
                params[param_name] = f"%{phrase}%"

            elif part.endswith("*"):
                # Partial word anywhere
                partial = part[:-1].strip()
                or_conditions.append(f"data::text ILIKE :{param_name}")
                params[param_name] = f"%{partial}%"

            else:
                # Whole word match
                pattern = f"\\m{part}\\M"
                or_conditions.append(f"data::text ~* :{param_name}")
                params[param_name] = pattern

        if or_conditions:
            keyword_clauses.append("(" + " OR ".join(or_conditions) + ")")

    if keyword_clauses:
        conditions.append(text(" AND ".join(keyword_clauses)))

    return conditions, params
