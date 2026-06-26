"""Tests for the MCP Streamable HTTP transport endpoint."""

import json

from fastapi.testclient import TestClient

from codegraphcontext.api.app import create_app

_ENDPOINT = "/api/v1/mcp/http"
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _parse_sse(text: str) -> dict:
    """Return the JSON payload from the first SSE ``data:`` line."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise AssertionError(f"no SSE data line in response: {text!r}")


def _initialize(client: TestClient) -> str:
    """Run the initialize handshake and return the session id."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.0"},
        },
    }
    resp = client.post(_ENDPOINT, json=body, headers=_HEADERS)
    assert resp.status_code == 200, resp.text
    session_id = resp.headers.get("mcp-session-id")
    assert session_id
    return session_id


def test_initialize_uses_exact_path_without_redirect():
    # The endpoint must answer on the exact path (no trailing-slash redirect),
    # since MCP clients POST to the configured URL verbatim.
    with TestClient(create_app()) as client:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.0.0"},
            },
        }
        resp = client.post(_ENDPOINT, json=body, headers=_HEADERS, follow_redirects=False)
        assert resp.status_code == 200, resp.text
        assert resp.headers.get("mcp-session-id")
        result = _parse_sse(resp.text)["result"]
        assert result["serverInfo"]["name"] == "CodeGraphContext"


def test_tools_list_returns_tools():
    with TestClient(create_app()) as client:
        session_id = _initialize(client)
        headers = {**_HEADERS, "mcp-session-id": session_id}

        client.post(
            _ENDPOINT,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
        )

        resp = client.post(
            _ENDPOINT,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        tools = _parse_sse(resp.text)["result"]["tools"]
        assert len(tools) > 0
