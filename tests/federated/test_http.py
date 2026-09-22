"""The shared outbound client: identity, timeouts, and the no-lifespan fallback."""

import httpx
import pytest
from fastapi import FastAPI

from bluecore_api.federated.http import USER_AGENT, client_for, new_client


def test_user_agent_identifies_us_and_how_to_get_in_touch():
    # id.loc.gov's robots.txt says access may be blocked for irresponsible use,
    # so an anonymous UA is the difference between an email and an IP block.
    assert USER_AGENT.startswith("BlueCore-API/")
    assert "bcld.info" in USER_AGENT
    assert "github.com/blue-core-lod/bluecore_api" in USER_AGENT


def test_client_has_explicit_bounded_timeouts():
    # httpx's default only bounds a single read; a hung connect or a slow pool
    # checkout would otherwise sit inside the request.
    client = new_client()
    timeout = client.timeout
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
        2.0,
        4.0,
        2.0,
        1.0,
    )
    # id.loc.gov 303-redirects a resource URI to its .jsonld representation.
    assert client.follow_redirects is True


@pytest.mark.asyncio
async def test_client_for_reuses_the_lifespan_client():
    app = FastAPI()
    shared = new_client()
    app.state.http_client = shared
    try:
        async with client_for(app) as client:
            assert client is shared
        # The lifespan owns it, so the request must not have closed it.
        assert not shared.is_closed
    finally:
        await shared.aclose()


@pytest.mark.asyncio
async def test_client_for_falls_back_and_cleans_up_when_there_is_no_lifespan():
    # ASGITransport-driven tests never run lifespan, so app.state has no client.
    app = FastAPI()
    async with client_for(app) as client:
        assert isinstance(client, httpx.AsyncClient)
        fallback = client
    assert fallback.is_closed


def test_lifespan_creates_the_client_through_the_keycloak_wrapper(keycloak_client):
    """End to end through the production wrapper chain.

    keycloak_client drives the app via BypassKeycloakForGet, the same wrapper
    uvicorn talks to in the deployed stack. If the wrapper choked on the
    lifespan scope, app.state.http_client would never be set.
    """
    from bluecore_api.app.main import base_app

    assert isinstance(base_app.state.http_client, httpx.AsyncClient)
    assert not base_app.state.http_client.is_closed
