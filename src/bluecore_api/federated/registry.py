"""Which sources exist, and which of them a given request queries.

Factories rather than instances: the sources need different collaborators (a
database Session, an HTTP client) and those are per-request.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from bluecore_api.federated.base import SearchSource
from bluecore_api.federated.config import enabled_source_ids
from bluecore_api.federated.sources.bluecore import BlueCoreSource
from bluecore_api.federated.sources.loc import LibraryOfCongressSource

logger = logging.getLogger(__name__)


@dataclass
class SourceContext:
    """Everything any source might need to do its work.

    A single bag so adding a source that needs, say, credentials does not
    change the factory signature for the ones that do not.
    """

    db: Session
    http: httpx.AsyncClient


SOURCE_FACTORIES: dict[str, Callable[[SourceContext], SearchSource]] = {
    BlueCoreSource.id: lambda ctx: BlueCoreSource(ctx.db),
    LibraryOfCongressSource.id: lambda ctx: LibraryOfCongressSource(ctx.http),
}


class UnknownSourceError(ValueError):
    """A caller asked for a source that does not exist."""


def known_source_ids() -> list[str]:
    return sorted(SOURCE_FACTORIES)


def configured_source_ids() -> list[str]:
    """Enabled sources, in response order.

    An unknown id in the environment is logged and skipped rather than raising:
    a typo in a deployment variable should not take the API down.
    """
    ids = []
    for source_id in enabled_source_ids():
        if source_id in SOURCE_FACTORIES:
            ids.append(source_id)
        else:
            logger.warning(
                "Ignoring unknown federated search source %r; known sources are %s",
                source_id,
                ", ".join(known_source_ids()),
            )
    return ids


def resolve_sources(
    ctx: SourceContext, requested: str | None = None
) -> list[SearchSource]:
    """Build the sources for one request.

    The environment sets the ceiling; a `sources=` parameter can only narrow
    it, so a client cannot switch on a source operations has turned off.
    """
    configured = configured_source_ids()
    if requested is None:
        chosen = configured
    else:
        asked = [part.strip() for part in requested.split(",") if part.strip()]
        unknown = [s for s in asked if s not in SOURCE_FACTORIES]
        if unknown:
            raise UnknownSourceError(
                f"Unknown source(s): {', '.join(unknown)}. "
                f"Known sources: {', '.join(known_source_ids())}."
            )
        chosen = [s for s in configured if s in asked]
    return [SOURCE_FACTORIES[source_id](ctx) for source_id in chosen]
