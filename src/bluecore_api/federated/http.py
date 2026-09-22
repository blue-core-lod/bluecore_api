"""The outbound HTTP client for federated search.

Blue Core's only other outbound caller is workflow.py, which talks to Airflow
on the internal network with no timeouts, no shared client, and a new
AsyncClient per call. None of that is safe against a third party, so this
module owns the client instead:

  - explicit timeouts, since httpx's 5s default is a single read bound
  - one client on the app lifespan, so connections are pooled and reused
  - a User-Agent that says who we are and how to reach us, because
    id.loc.gov's robots.txt warns it will block irresponsible clients
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

import httpx
from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Bounds each socket operation. The whole-source budget (which also covers
# redirects and JSON parsing) is enforced separately by the orchestrator.
TIMEOUT = httpx.Timeout(connect=2.0, read=4.0, write=2.0, pool=1.0)

LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=5)

USER_AGENT = (
    f"BlueCore-API/{version('bluecore-api')} (+https://bcld.info/; "
    "federated search; https://github.com/blue-core-lod/bluecore_api)"
)


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        limits=LIMITS,
        headers={"User-Agent": USER_AGENT},
        # id.loc.gov 303-redirects a resource URI to its .jsonld representation.
        follow_redirects=True,
        max_redirects=3,
    )


@asynccontextmanager
async def client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Yield the lifespan client, or a short-lived one when there isn't one.

    The fallback is not defensive padding: the async test fixtures drive the
    app through ASGITransport, which does not run lifespan, so app.state has no
    client there. A module-level singleton is not an option either -- an
    AsyncClient's pool binds to the event loop it first ran on, and
    pytest-asyncio gives each test a new loop.

    Only the fallback client is closed; the lifespan one outlives the request.
    """
    client = getattr(app.state, "http_client", None)
    if client is not None:
        yield client
        return

    logger.debug("No lifespan http client; using a per-request client")
    async with new_client() as fallback:
        yield fallback
