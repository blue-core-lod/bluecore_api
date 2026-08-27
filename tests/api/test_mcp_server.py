"""
Unit tests for the MCP (Model Context Protocol) server integration.
"""

import pytest


@pytest.fixture(autouse=True)
def _fresh_mcp_transport():
    """Give each test a fresh MCP session manager."""
    from bluecore_api.app.main import mcp

    transport = mcp._http_transport
    transport._manager_started = False
    transport._session_manager = None
    transport._manager_task = None
    yield


def test_mcp_get_is_public(keycloak_client):
    """GET /mcp is public (no auth) and reaches the MCP app."""
    response = keycloak_client.get("/mcp")
    # 406 is the EXPECTED success signal here, not a failure: the GET cleared auth
    # (BypassKeycloakForGet let it through) and reached the MCP app, which then
    # rejected the bare request because MCP's SSE transport requires
    # `Accept: text/event-stream`. The JSON-RPC -32600 below confirms the response
    # came from MCP itself. (If /mcp were NOT public, Keycloak would return 401.)
    assert response.status_code == 406
    assert response.json()["error"]["code"] == -32600


MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _initialize(client, headers=None):
    """Open an MCP session and return the response."""
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
        "id": 1,
    }
    return client.post("/mcp", json=payload, headers={**MCP_HEADERS, **(headers or {})})


def _tools_call(client, tool, headers=None, session_id=None):
    """Invoke an MCP tool by name."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool, "arguments": {}},
        "id": 2,
    }
    request_headers = {**MCP_HEADERS, **(headers or {})}
    if session_id:
        request_headers["mcp-session-id"] = session_id
    return client.post("/mcp", json=payload, headers=request_headers)


def test_mcp_initialize_is_public(keycloak_client):
    """
    Anonymous POST /mcp initialize succeeds.

    MCP POSTs every message, so requiring a token here would mean no client
    could connect at all without one — which is what broke Claude Desktop: the
    401 sent it into an OAuth discovery flow that dead-ends on Nginx error pages.
    """
    response = _initialize(keycloak_client)
    assert response.status_code == 200


def test_mcp_tools_list_is_public(keycloak_client):
    """
    Anonymous tools/list succeeds.

    Letting `initialize` through alone isn't enough: tools/list is also a POST,
    so gating it would connect the client to a server showing zero tools.
    """
    payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}
    response = keycloak_client.post("/mcp", json=payload, headers=MCP_HEADERS)
    assert response.status_code != 403


def test_mcp_anonymous_read_only_tool_is_allowed(keycloak_client):
    """
    A tool backed by a GET endpoint clears the permission gate anonymously,
    matching the REST API beside it, where GETs are public.
    """
    session_id = _initialize(keycloak_client).headers.get("mcp-session-id")
    response = _tools_call(keycloak_client, "get_work", session_id=session_id)
    assert response.status_code != 403


def test_mcp_anonymous_write_tool_is_rejected(keycloak_client):
    """A destructive tool still needs create/update, POST body notwithstanding."""
    session_id = _initialize(keycloak_client).headers.get("mcp-session-id")
    response = _tools_call(keycloak_client, "delete_work", session_id=session_id)
    assert response.status_code == 403


def test_mcp_write_tool_without_required_permissions(keycloak_client):
    """An authenticated user with no create/update role is denied a write tool."""
    session_id = _initialize(keycloak_client).headers.get("mcp-session-id")
    # public user has no special roles
    response = _tools_call(
        keycloak_client,
        "create_hub",
        headers={"X-User": "public"},
        session_id=session_id,
    )
    assert response.status_code == 403


def test_mcp_write_tool_with_permissions_clears_gate(keycloak_client):
    """A cataloger keeps write access — unchanged by the anonymous read path."""
    session_id = _initialize(keycloak_client).headers.get("mcp-session-id")
    response = _tools_call(
        keycloak_client,
        "create_hub",
        headers={"X-User": "cataloger"},
        session_id=session_id,
    )
    assert response.status_code != 403


def test_mcp_read_only_tools_are_derived_from_get_routes():
    """
    The read-only list comes from the mount's operation map, so a new endpoint
    can't drift out of step with the gate — and a misleading name can't fool it:
    `get_works` is a POST that creates a Work.
    """
    from bluecore_api.app.main import _MCP_READ_ONLY_TOOLS, mcp

    assert "get_work" in _MCP_READ_ONLY_TOOLS
    assert "search" in _MCP_READ_ONLY_TOOLS
    assert "get_works" not in _MCP_READ_ONLY_TOOLS  # POST /works/, creates
    assert "delete_work" not in _MCP_READ_ONLY_TOOLS
    assert "create_hub" not in _MCP_READ_ONLY_TOOLS
    assert _MCP_READ_ONLY_TOOLS == {
        name
        for name, operation in mcp.operation_map.items()
        if operation["method"].upper() == "GET"
    }


def test_mcp_delete_session_is_public(keycloak_client):
    """
    DELETE /mcp ends the caller's own session and changes no data, so an
    anonymous client can disconnect cleanly instead of leaking a session.
    """
    session_id = _initialize(keycloak_client).headers.get("mcp-session-id")
    response = keycloak_client.request(
        "DELETE", "/mcp", headers={**MCP_HEADERS, "mcp-session-id": session_id or ""}
    )
    assert response.status_code not in (401, 403)


def test_mcp_post_with_permissions_clears_gate(keycloak_client):
    """
    POST /mcp as a create/update user passes the keyclaok auth and reaches the MCP app.

    This is also the canary for body replay: `mcp_permissions` reads the JSON-RPC
    body before the mount does, so a 200 here means it put the body back.
    """
    response = _initialize(keycloak_client, headers={"X-User": "cataloger"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_mcp_list_tools_request(mcp_client):
    """Test listing available MCP tools."""
    client, headers = mcp_client

    # Request the tools list
    tools_payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}

    response = await client.post("/mcp", json=tools_payload, headers=headers)

    assert response.status_code == 200

    data = response.json()
    tools = sorted(data["result"]["tools"], key=lambda x: x["name"])
    assert len(tools) == 39
    assert tools[0]["name"].startswith("batch_upload")
