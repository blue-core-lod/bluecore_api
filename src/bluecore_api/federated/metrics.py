"""Counters for the federated search experiment.

The question this feature exists to answer is not "does it work" -- it does --
but "how much of an external corpus would we actually be serving?" If
catalogers touch ten thousand LC records over a few months, loading forty-seven
million to serve them is a ratio worth putting in front of the team. That
argument can only be made from data collected before the decision.

Two deliberate limits, both worth knowing when reading the numbers:

  - These are per-process and reset on restart, like the cache. The durable
    record is the structured log line emitted alongside each event; this module
    is a live view, not a store.
  - "Touched" here means fetched for editing. Whether a record was ultimately
    *saved* cannot be counted yet: the editor posts a blank-node subject, so
    nothing on the write path knows which external record a new resource came
    from. See docs/federated-search.md on the provenance decision.
"""

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Distinct URIs are held in a set, which is bounded here so a long-running
# process cannot grow one without limit. Once the cap is hit the count stops
# rising and `capped` says so, rather than quietly under-reporting.
MAX_TRACKED_URIS = 100_000


@dataclass
class _Counters:
    searches: int = 0
    source_outcomes: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    seen_uris: set[str] = field(default_factory=set)
    fetched_uris: set[str] = field(default_factory=set)
    seen_capped: bool = False
    fetched_capped: bool = False


_lock = threading.Lock()
_counters = _Counters()


def reset() -> None:
    """Tests must call this between cases; this is module state."""
    global _counters
    with _lock:
        _counters = _Counters()


def _track(uris: set[str], value: str) -> bool:
    """Add a URI, returning whether the set is now at its cap."""
    if len(uris) >= MAX_TRACKED_URIS:
        return True
    uris.add(value)
    return False


def record_search(outcomes: dict[str, str], external_uris: list[str]) -> None:
    """One federated search: which sources answered, and what came back."""
    with _lock:
        _counters.searches += 1
        for source_id, status in outcomes.items():
            key = f"{source_id}:{status}"
            _counters.source_outcomes[key] = _counters.source_outcomes.get(key, 0) + 1
        for uri in external_uris:
            _counters.seen_capped |= _track(_counters.seen_uris, uri)

    logger.info(
        "federated.search outcomes=%s results=%d",
        ",".join(f"{k}={v}" for k, v in sorted(outcomes.items())),
        len(external_uris),
    )


def record_fetch(uri: str, *, already_held: bool) -> None:
    """One external record opened for editing -- the number that matters."""
    with _lock:
        _counters.fetched_capped |= _track(_counters.fetched_uris, uri)

    logger.info("federated.fetch uri=%s already_held=%s", uri, already_held)


def record_cache(*, hit: bool) -> None:
    with _lock:
        if hit:
            _counters.cache_hits += 1
        else:
            _counters.cache_misses += 1


def snapshot() -> dict[str, object]:
    with _lock:
        requests = _counters.cache_hits + _counters.cache_misses
        return {
            "searches": _counters.searches,
            "source_outcomes": dict(sorted(_counters.source_outcomes.items())),
            "distinct_external_records_seen": len(_counters.seen_uris),
            "distinct_external_records_seen_capped": _counters.seen_capped,
            "distinct_external_records_fetched": len(_counters.fetched_uris),
            "distinct_external_records_fetched_capped": _counters.fetched_capped,
            "upstream_cache_hits": _counters.cache_hits,
            "upstream_cache_misses": _counters.cache_misses,
            "upstream_cache_hit_rate": (
                round(_counters.cache_hits / requests, 3) if requests else None
            ),
        }
