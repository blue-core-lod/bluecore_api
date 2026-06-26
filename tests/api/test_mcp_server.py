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


def test_mcp_post_without_auth_is_rejected_by_keycloak(keycloak_client):
    """Anonymous POST /mcp is not bypassed, so Keycloak rejects it with 401."""
    payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
    response = keycloak_client.post("/mcp", json=payload)
    assert response.status_code == 401


def test_mcp_without_required_permissions(keycloak_client):
    """Test that MCP access is denied without create/update permissions."""
    payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
    headers = {"X-User": "public"}  # public user has no special roles
    response = keycloak_client.post("/mcp", json=payload, headers=headers)
    # Should be denied without required permissions
    assert response.status_code == 403


def test_mcp_post_with_permissions_clears_gate(keycloak_client):
    """
    POST /mcp as a create/update user passes the keyclaok auth and reaches the MCP app.
    """
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
    headers = {
        "X-User": "cataloger",
        "Accept": "application/json, text/event-stream",
    }
    response = keycloak_client.post("/mcp", json=payload, headers=headers)
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
    assert len(tools) == 28
    assert tools[0]["name"].startswith("batch_upload")
