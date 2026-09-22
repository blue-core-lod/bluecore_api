"""The TTL cache and its single-flight coalescing."""

import asyncio

import pytest

from bluecore_api.federated import cache


@pytest.fixture(autouse=True)
def clean_cache():
    """Module state. Without this a test passes alone and fails in suite order."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.asyncio
async def test_a_second_call_does_not_refetch():
    calls = []

    async def fetch():
        calls.append(1)
        return "value"

    assert await cache.cached("k", fetch) == "value"
    assert await cache.cached("k", fetch) == "value"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_entries_expire(monkeypatch):
    monkeypatch.setenv("FEDERATED_SEARCH_CACHE_TTL", "0")
    calls = []

    async def fetch():
        calls.append(1)
        return len(calls)

    assert await cache.cached("k", fetch) == 1
    assert await cache.cached("k", fetch) == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_request():
    """The point of coalescing: a TTL cache misses for all of these, because
    none of them has finished yet."""
    calls = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch():
        calls.append(1)
        started.set()
        await release.wait()
        return "value"

    first = asyncio.ensure_future(cache.cached("k", fetch))
    await started.wait()
    rest = [asyncio.ensure_future(cache.cached("k", fetch)) for _ in range(4)]
    await asyncio.sleep(0)
    release.set()

    assert await first == "value"
    assert await asyncio.gather(*rest) == ["value"] * 4
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failures_are_not_cached():
    """A brief upstream outage should recover on the next search rather than
    stay broken for the length of the TTL."""
    calls = []

    async def failing():
        calls.append(1)
        raise RuntimeError("upstream down")

    async def working():
        return "value"

    with pytest.raises(RuntimeError):
        await cache.cached("k", failing)
    assert await cache.cached("k", working) == "value"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_in_flight_entries_are_released():
    async def fetch():
        return "value"

    await cache.cached("k", fetch)

    assert cache.stats() == {"entries": 1, "in_flight": 0}


@pytest.mark.asyncio
async def test_oldest_entries_are_evicted(monkeypatch):
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2)

    async def fetch():
        return "value"

    for key in ("a", "b", "c"):
        await cache.cached(key, fetch)

    assert cache.stats()["entries"] == 2


@pytest.mark.asyncio
async def test_hits_and_misses_are_counted():
    """The hit rate is one of the numbers the experiment is meant to produce."""
    from bluecore_api.federated import metrics

    metrics.reset()

    async def fetch():
        return "value"

    await cache.cached("k", fetch)
    await cache.cached("k", fetch)

    counts = metrics.snapshot()
    assert counts["upstream_cache_misses"] == 1
    assert counts["upstream_cache_hits"] == 1
    assert counts["upstream_cache_hit_rate"] == 0.5
