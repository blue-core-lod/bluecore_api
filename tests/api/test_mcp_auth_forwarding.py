"""
MCP tool calls must reach protected routes as the authenticated caller.

fastapi_mcp forwards the Authorization header, but it invokes each tool by
calling base_app directly, which skips the KeycloakMiddleware wrapped around
it in main.py. The route then sees no user and answers 401, which is what
write tools return on stage even with a valid token.

The other MCP tests can't see this: the `app` fixture overrides get_user and
get_auth on base_app, and those overrides apply to the internal call too.
"""

import json

import pytest
from fastapi.responses import JSONResponse
from fastapi_keycloak_middleware import FastApiUser, get_auth, get_user
from httpx import ASGITransport, AsyncClient


class _StubKeycloakToken:
    """
    Stand-in for KeycloakMiddleware that decodes a bearer token into the scope.

    Unlike the dependency overrides on `app`, this only authenticates requests
    that actually pass through it, the way the real middleware does.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        authorization = dict(scope.get("headers") or ()).get(b"authorization")
        if authorization == b"Bearer cataloger":
            scope["user"] = FastApiUser("Jon", "Doe", "cataloger")
            scope["auth"] = ["create", "export", "update"]
            await self.app(scope, receive, send)
        else:
            await JSONResponse({"detail": "Not authenticated"}, status_code=401)(
                scope, receive, send
            )


@pytest.fixture(autouse=True)
def _fresh_mcp_transport():
    """Give each test a fresh MCP session manager."""
    from bluecore_api.app.main import mcp

    transport = mcp._http_transport
    transport._manager_started = False  # ty: ignore[invalid-assignment]
    transport._session_manager = None  # ty: ignore[invalid-assignment]
    transport._manager_task = None  # ty: ignore[invalid-assignment]
    yield


@pytest.mark.asyncio
async def test_mcp_tool_call_forwards_token_to_route(client, app, monkeypatch):
    from bluecore_api.app import main

    created = client.post(
        "/profiles/",
        headers={"X-User": "cataloger"},
        json={"data": json.dumps({"label": "To Be Deleted Over MCP"})},
    ).json()
    profile_uuid = created["uuid"]

    # From here on, auth comes only from what the (stub) middleware puts in the
    # scope, as it does in production.
    monkeypatch.delitem(app.dependency_overrides, get_user)
    monkeypatch.delitem(app.dependency_overrides, get_auth)
    monkeypatch.setattr(
        main.middleware_wrapped_app,
        "keycloak_middleware",
        _StubKeycloakToken(main.base_app),
    )

    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer cataloger",
    }
    transport = ASGITransport(main.application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
            "id": 1,
        }
        init_response = await ac.post("/mcp", json=init_payload, headers=headers)
        assert init_response.status_code == 200
        headers["mcp-session-id"] = init_response.headers["mcp-session-id"]

        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        await ac.post("/mcp", json=initialized, headers=headers)

        call_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "delete_profile",
                "arguments": {"profile_uuid": profile_uuid},
            },
            "id": 2,
        }
        response = await ac.post("/mcp", json=call_payload, headers=headers)

    assert response.status_code == 200
    result = response.json()["result"]
    text = "\n".join(c.get("text", "") for c in result["content"])
    assert not result["isError"], text

    assert client.get(f"/profiles/{profile_uuid}").status_code == 404
