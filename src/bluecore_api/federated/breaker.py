"""Stop asking a source that has stopped answering.

Without this, a source that is down costs every search its full timeout --
five seconds added to every query, for as long as the outage lasts, on a page
a cataloger is waiting for. Failing fast and saying so is both quicker and
more honest.

Deliberately per-process and in memory, like the cache: this is about not
wasting a request, not about distributed consensus. Several workers each
discovering the outage separately is fine.
"""

import logging
import time
from dataclasses import dataclass

from bluecore_api.federated.config import (
    breaker_cooldown_seconds,
    breaker_threshold,
)

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """The source is being skipped because it has been failing."""


@dataclass
class _State:
    consecutive_failures: int = 0
    opened_at: float | None = None


_states: dict[str, _State] = {}


def reset() -> None:
    """Tests must call this between cases; this is module state."""
    _states.clear()


def _state(source_id: str) -> _State:
    return _states.setdefault(source_id, _State())


def is_open(source_id: str) -> bool:
    """Whether to skip this source for now.

    A single request is let through once the cooldown expires -- if it
    succeeds the breaker closes, if it fails the cooldown starts again.
    """
    state = _state(source_id)
    if state.opened_at is None:
        return False
    if time.monotonic() - state.opened_at >= breaker_cooldown_seconds():
        logger.info("Cooldown elapsed for %s; letting one request through", source_id)
        state.opened_at = None
        return False
    return True


def record_success(source_id: str) -> None:
    state = _state(source_id)
    if state.consecutive_failures or state.opened_at is not None:
        logger.info("Source %s is answering again", source_id)
    state.consecutive_failures = 0
    state.opened_at = None


def record_failure(source_id: str) -> None:
    state = _state(source_id)
    state.consecutive_failures += 1
    if state.consecutive_failures >= breaker_threshold() and state.opened_at is None:
        state.opened_at = time.monotonic()
        logger.warning(
            "Skipping %s for %gs after %d consecutive failures",
            source_id,
            breaker_cooldown_seconds(),
            state.consecutive_failures,
        )
