"""
Unit tests for the MCP (Model Context Protocol) server integration.
"""

import pytest


def test_mcp_endpoint_exists(client):
    """Test that the /mcp endpoint is mounted and accessible."""
    response = client.get("/mcp")
    # The MCP endpoint exists and requires authentication, so expects 403
    assert response.status_code == 403


def test_mcp_endpoint_post_without_auth(client):
    """Test that MCP endpoint requires authentication for POST requests."""
    payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
    response = client.post("/mcp", json=payload)
    # Should fail without proper authentication (create/update permissions)
    assert response.status_code == 403


def test_mcp_without_required_permissions(client):
    """Test that MCP access is denied without create/update permissions."""
    payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
    headers = {"X-User": "public"}  # public user has no special roles
    response = client.post("/mcp", json=payload, headers=headers)
    # Should be denied without required permissions
    assert response.status_code == 403


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
    assert len(tools) == 24
    assert tools[0]["name"].startswith("batch_upload")
