"""Wire format for federated search.

Results are grouped by source, not merged. A group carries its own total,
status and paging links, so a source that timed out stays distinguishable from
a source that matched nothing -- the failure that otherwise leads a cataloger
to conclude no record exists and hand-catalog a duplicate.

FederatedResultSchema is a strict superset of ResourceBaseSchema's field names
(schemas.py:16), on purpose: sinopia_editor's hitsToResult
(sinopiaSearch.js:175) already reads uri, data.title[].mainTitle,
data.contribution[].agent.label, data["@type"], created_at and updated_at, so a
client can hand a group's results straight to it. It is not a subclass --
ResourceBaseSchema carries from_attributes=True and ORM semantics that do not
apply to a record we do not hold, and subclassing would assert an is-a
relationship in the OpenAPI schema that is not true.

Unlike the rest of the API these models are serialized with
response_model_exclude_none=False. An explicit "local_uri": null means "we
checked, we do not have it", which a missing key cannot say.
"""

from datetime import datetime
from enum import StrEnum, auto

from pydantic import BaseModel, Field


class SourceStatus(StrEnum):
    """How a source's group turned out."""

    OK = auto()
    TIMEOUT = auto()
    ERROR = auto()
    UNSUPPORTED = auto()
    # Skipped without asking, because it has been failing. Distinct from ERROR:
    # nothing went wrong on this request.
    UNAVAILABLE = auto()


class FederatedResultSchema(BaseModel):
    """One hit from one source."""

    source: str = Field(description="Source id, e.g. 'bluecore' or 'loc'.")
    source_label: str = Field(description="Human name of the source.")
    uri: str = Field(
        description=(
            "The record's own URI at its source. For an external record this is "
            "the external URI, never a Blue Core proxy URL -- see proxy_uri."
        )
    )
    type: str = Field(description="works, instances or hubs.")
    data: dict[str, object] = Field(
        description=(
            "JSON-LD for the hit. For Blue Core records this is the stored "
            "document. For an external record it is a summary synthesized from "
            "the source's search response, not the source's full record."
        )
    )
    id: int | None = Field(default=None, description="Blue Core row id, if ours.")
    uuid: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    local_uri: str | None = Field(
        default=None,
        description=(
            "The Blue Core resource already derived from this record, found via "
            "its bf:derivedFrom provenance. Null means we hold no copy."
        ),
    )
    proxy_uri: str | None = Field(
        default=None,
        description="Where to fetch the full external record through this API.",
    )
    rank: float | None = Field(
        default=None,
        description=(
            "The source's own score. Comparable only against other results from "
            "the same source; the sources do not share a scale."
        ),
    )
    related: dict[str, str] = Field(
        default_factory=dict,
        description="Related record URIs the source volunteered, e.g. an instance.",
    )


class FederatedLinksSchema(BaseModel):
    """Paging links for one source's group.

    Every field is optional, unlike LinksSchema: there is no global result list
    to page, so there is no first link that always exists.
    """

    first: str | None = None
    prev: str | None = None
    next: str | None = None


class FederatedSourceSchema(BaseModel):
    """One source's contribution to a search."""

    id: str
    label: str
    status: SourceStatus
    error: str | None = Field(
        default=None,
        description="Why the source failed, phrased for a cataloger to read.",
    )
    total: int | None = Field(
        default=None, description="Matches the source claims to have."
    )
    total_is_exact: bool = Field(
        default=False,
        description="True for a counted total, false for an upstream estimate.",
    )
    elapsed_ms: int = Field(description="Wall-clock time this source took.")
    truncated: bool = Field(
        default=False,
        description="The source declined to run, e.g. paging too deep into it.",
    )
    note: str | None = Field(
        default=None, description="Caveats needed to read this group correctly."
    )
    links: FederatedLinksSchema = Field(default_factory=FederatedLinksSchema)
    results: list[FederatedResultSchema] = Field(default_factory=list)


class FederatedSearchResultSchema(BaseModel):
    """A federated search, grouped by source."""

    q: str
    type: str
    scope: str
    limit: int
    offset: int
    total: int = Field(
        description=(
            "Sum of the per-source totals. Records held in Blue Core and still "
            "present at their source are counted twice; local_uri is how a "
            "client shows that overlap, page by page."
        )
    )
    total_is_estimate: bool = Field(
        default=True,
        description="True whenever any contributing total is an estimate.",
    )
    partial: bool = Field(
        default=False, description="At least one source failed or was skipped."
    )
    sources: list[FederatedSourceSchema]
