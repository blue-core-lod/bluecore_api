"""Blue Core's own Postgres, as a federated source.

This deliberately calls the same helpers GET /search/ uses rather than
reimplementing the query, so the two cannot drift: a change to query parsing or
ranking shows up in both endpoints or neither.
"""

import asyncio

from bluecore_models.models import ResourceBase
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.app.routes.search import (
    apply_resource_search,
    create_count_query,
    get_types,
)
from bluecore_api.constants import CONTEXT_URL, SearchType
from bluecore_api.federated.base import (
    FederatedQuery,
    FederatedResult,
    SourceResults,
)

SOURCE_ID = "bluecore"
SOURCE_LABEL = "Blue Core"


def jsonld_document(value: object) -> dict[str, object]:
    """Narrow a stored JSONB column to the mapping it actually holds.

    bluecore-models annotates ResourceBase.data as Mapped[bytes] (resource.py:17)
    though psycopg2 hands back the decoded document. Elsewhere in this codebase
    that is papered over with per-line type-checker ignores; check it instead,
    so a genuinely unexpected shape surfaces as an error rather than as a
    confusing failure further down.
    """
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON-LD object, got {type(value).__name__}")
    return value


class BlueCoreSource:
    """The local index."""

    id = SOURCE_ID
    label = SOURCE_LABEL
    supported_types = frozenset(SearchType)

    def __init__(self, db: Session):
        self.db = db

    async def search(self, query: FederatedQuery) -> SourceResults:
        # psycopg2 is synchronous and would otherwise block the event loop for
        # the whole query, serializing the fan-out: latency would become
        # local + remote instead of max(local, remote). One worker thread
        # touches the Session at a time and the coroutine awaits, which is the
        # supported pattern -- do not hand the same Session to two of these.
        # Note anyio's default limiter allows 40 threads while the engine is
        # pool_size=5, max_overflow=5 (database.py:15), so under real
        # concurrency threads would queue on the pool rather than on Postgres.
        return await asyncio.to_thread(self._search_sync, query)

    def _search_sync(self, query: FederatedQuery) -> SourceResults:
        stmt = select(ResourceBase).where(ResourceBase.type.in_(get_types(query.type)))
        stmt, _has_search_query = apply_resource_search(stmt, query.q, query.scope)
        total = self.db.scalar(create_count_query(stmt))
        rows = (
            self.db.execute(stmt.offset(query.offset).limit(query.limit))
            .scalars()
            .all()
        )
        return SourceResults(
            results=[self._to_result(row) for row in rows],
            total=total,
            total_is_exact=True,
        )

    def _to_result(self, row: ResourceBase) -> FederatedResult:
        data = dict(jsonld_document(row.data))
        # Matches GET /search/, which injects the context per result rather
        # than storing it (search.py:247).
        data["@context"] = CONTEXT_URL
        return FederatedResult(
            source=self.id,
            source_label=self.label,
            uri=row.uri,
            type=row.type,
            data=data,
            id=row.id,
            uuid=str(row.uuid) if row.uuid else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            # A Blue Core record is already local; saying so keeps clients from
            # having to special-case which sources can populate this.
            local_uri=row.uri,
        )
