"""A small TTL cache with single-flight coalescing for outbound search calls.

Deliberately in-process. Redis would be a stateful dependency, an ops runbook
and a new failure mode in exchange for what fits here in a few dozen lines, and
a per-worker cache is fine for this: the point is politeness to upstreams, not
a globally consistent view. id.loc.gov serves these responses with
cache-control: public, max-age=2419200 and its own Varnish already returns warm
repeats in about a tenth of the time, so a short local TTL is conservative.

The coalescing matters more than the TTL. Catalogers fire the same query from
several tabs at once and a plain TTL cache misses on all of them, because none
has finished yet. Sharing one in-flight request is what keeps a burst of
interest from becoming a burst of traffic.

The raw upstream payload is what gets cached, not the mapped results, so fixing
a mapping bug takes effect immediately instead of being masked by stale objects.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from bluecore_api.federated.config import cache_ttl_seconds

logger = logging.getLogger(__name__)

MAX_ENTRIES = 512

_entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_in_flight: dict[str, asyncio.Future] = {}


def clear() -> None:
    """Drop everything. Tests must call this between cases -- this is module
    state, and without it a test passes alone and fails in suite order."""
    _entries.clear()
    _in_flight.clear()


def stats() -> dict[str, int]:
    return {"entries": len(_entries), "in_flight": len(_in_flight)}


def _get(key: str) -> tuple[bool, Any]:
    entry = _entries.get(key)
    if entry is None:
        return False, None
    expires_at, value = entry
    if expires_at <= time.monotonic():
        del _entries[key]
        return False, None
    _entries.move_to_end(key)
    return True, value


def _put(key: str, value: Any) -> None:
    _entries[key] = (time.monotonic() + cache_ttl_seconds(), value)
    _entries.move_to_end(key)
    while len(_entries) > MAX_ENTRIES:
        _entries.popitem(last=False)


async def cached(key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
    """Return the cached value for `key`, fetching it at most once.

    A second caller arriving while the first request is still open awaits that
    request rather than starting its own. Failures are not cached: an upstream
    that is briefly down should recover on the next search, not stay broken for
    the length of a TTL.
    """
    hit, value = _get(key)
    if hit:
        return value

    existing = _in_flight.get(key)
    if existing is not None:
        logger.debug("Joining in-flight request for %s", key)
        return await asyncio.shield(existing)

    task = asyncio.ensure_future(fetch())
    _in_flight[key] = task
    try:
        value = await task
    finally:
        _in_flight.pop(key, None)
    _put(key, value)
    return value
