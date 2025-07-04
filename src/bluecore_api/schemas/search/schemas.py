from fastapi import Query
from typing import List, Optional, Annotated
from dataclasses import dataclass


@dataclass
class SearchParams:
    resource_type: Annotated[
        str,
        Query(
            alias="type",
            description="Resource type: works, instances, or all",
            min_length=1,
            max_length=15,
        ),
    ] = "all"

    keywords: Annotated[
        List[str],
        Query(
            alias="keyword",
            description="Keyword Search: Use `ILIKE` across all JSONB data",
        ),
    ] = ()

    uuid: Annotated[
        Optional[str],
        Query(description="Match native UUID column", min_length=1, max_length=500),
    ] = None

    rdf_id: Annotated[
        Optional[str], Query(description="RDF ID", min_length=1, max_length=150)
    ] = None

    rdf_type: Annotated[
        Optional[str], Query(description="RDF @type", min_length=1, max_length=50)
    ] = None

    mainTitle: Annotated[
        Optional[str], Query(description="Exact title", min_length=1, max_length=300)
    ] = None

    derivedFrom: Annotated[
        Optional[str],
        Query(description="Derived from URI", min_length=1, max_length=300),
    ] = None

    uri: Annotated[Optional[str], Query(description="Match native URI column")] = None

    keys: Annotated[List[str], Query(alias="key", description="Dynamic keys")] = ()

    values: Annotated[
        List[str], Query(alias="value", description="Dynamic values")
    ] = ()
