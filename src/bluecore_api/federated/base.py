"""The contract every federated search source implements.

A Protocol rather than an ABC: the sources have nothing to share at runtime.
The local one needs a database Session, the remote ones need an HTTP client,
and nothing ever does an isinstance check on them.

Adapters raise on failure and know nothing about status, timing, or error
strings -- the orchestrator in routes.py owns all of that, so every source
fails the same way and one adapter cannot decide to report "ok" for a half
empty result.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from bluecore_api.constants import SearchScope, SearchType


class FederatedSearchError(Exception):
    """A source could not answer. Carries a message meant for a cataloger."""


@dataclass(frozen=True)
class FederatedQuery:
    """One search, as every source sees it.

    An object rather than five arguments so a source that later needs, say,
    scope handling does not churn every signature in the chain.
    """

    q: str
    type: SearchType
    scope: SearchScope
    limit: int
    offset: int


@dataclass
class FederatedResult:
    """One hit, normalized.

    The field names deliberately match ResourceBaseSchema (schemas.py:16) and
    what sinopia_editor's hitsToResult reads (sinopiaSearch.js:175), so an
    external hit can render in the existing results table. See
    schemas/federated.py for the wire format and why they match.
    """

    source: str
    source_label: str
    uri: str
    type: str
    data: dict[str, object]
    id: int | None = None
    uuid: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # The Blue Core resource derived from this one, when we already hold a copy.
    local_uri: str | None = None
    # Where to fetch the full record when it is not ours to serve directly.
    proxy_uri: str | None = None
    # A source's own score. Only ever compared within that source's group; see
    # sources/loc.py on why cross-source comparison is not meaningful.
    rank: float | None = None
    related: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceResults:
    """What one source found.

    total is the source's own claim about how many matches exist, and is None
    for a source that cannot say. total_is_exact separates a COUNT(*) from an
    upstream estimate.
    """

    results: list[FederatedResult]
    total: int | None = None
    total_is_exact: bool = False
    # Set when the source refused to run rather than returning an empty page,
    # e.g. an offset beyond the external deep-paging cap.
    truncated: bool = False
    # Anything the cataloger needs to know to read the group correctly, such as
    # a source that only covers part of the requested type.
    note: str | None = None


@runtime_checkable
class SearchSource(Protocol):
    """A pool of BIBFRAME that federated search can query."""

    id: str
    """Stable identifier, used in FEDERATED_SEARCH_SOURCES and in the JSON."""

    label: str
    """Human name, shown to catalogers and used in error messages."""

    supported_types: frozenset[SearchType]
    """A source asked for a type outside this set reports "unsupported" rather
    than disappearing from the response: a missing group reads as "no results"."""

    async def search(self, query: FederatedQuery) -> SourceResults: ...
