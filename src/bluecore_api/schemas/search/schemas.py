"""
# ==============================================================================
# Pydantic schema for /search.
# Defines all user-facing query params.
# FastAPI auto-generates OpenAPI docs and does runtime validation.
# ------------------------------------------------------------------------------
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class SearchParams(BaseModel):
    resource_type: str = Field(
        default="all",
        alias="type",
        description="Resource type: works, instances, or all",
        min_length=1,
        max_length=15,
    )
    uuid: Optional[str] = Field(
        None,
        description="Match native UUID column",
        min_length=1,
        max_length=500,
    )
    rdf_id: Optional[str] = Field(
        None, description="RDF ID", min_length=1, max_length=150
    )
    rdf_type: Optional[str] = Field(
        None, description="RDF @type", min_length=1, max_length=50
    )
    mainTitle: Optional[str] = Field(
        None, description="Exact title", min_length=1, max_length=300
    )
    derivedFrom: Optional[str] = Field(
        None,
        description="Derived from URI",
        min_length=1,
        max_length=300,
    )
    uri: Optional[str] = Field(None, description="Match native URI column")
    keys: List[str] = Field(default=[], alias="key", description="Dynamic keys")
    values: List[str] = Field(default=[], alias="value", description="Dynamic values")
