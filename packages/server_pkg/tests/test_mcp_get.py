"""Tests for the MCP server GET endpoint (http_stream_transport.app).

The GET endpoint opens an SSE stream for server-initiated messages.
It validates the Accept header and respects the enable_sse_endpoint setting.
"""

import pytest
from unittest.mock import patch

from starlette.testclient import TestClient

from http_stream_transport.server.app import app
from http_stream_transport.server.session import clear_all_sessions

client = TestClient(app)

ENDPOINT = "/mcp"
VALID_TOKEN = "tok-acme-001"
VALID_TOKEN_B = "tok-globex-002"
AUTH_HEADER = {"Authorization": f"Bearer {VALID_TOKEN}"}
POST_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
GET_HEADERS = {"Accept": "text/event-stream"}


def make_initialize_request(id: int = 1):
    """Create an MCP initialize request."""
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": id,
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1.0"},
        },
    }


@pytest.fixture(autouse=True)
def _clean_sessions():
    clear_all_sessions()
    yield
    clear_all_sessions()


# ---------------------------------------------------------------------------
# Accept header validation — must include text/event-stream
# ---------------------------------------------------------------------------


def test_get_missing_accept_rejected():
    """No Accept header → 406."""
    resp = client.get(ENDPOINT, headers=AUTH_HEADER)
    assert resp.status_code == 406


def test_get_wrong_accept_rejected():
    """Accept without text/event-stream → 406."""
    resp = client.get(ENDPOINT, headers={"Accept": "application/json", **AUTH_HEADER})
    assert resp.status_code == 406


# ---------------------------------------------------------------------------
# SSE setting — enable_sse_endpoint
# ---------------------------------------------------------------------------


def test_get_sse_disabled_returns_405():
    """Valid Accept but SSE is disabled (the default) → 405."""
    resp = client.get(ENDPOINT, headers={"Accept": "text/event-stream", **AUTH_HEADER})
    assert resp.status_code == 405


def test_get_sse_enabled():
    """Valid Accept and SSE enabled → 200 with SSE content-type."""
    with patch("http_stream_transport.server.mcp_router.settings") as mock_settings:
        mock_settings.enable_sse_get_endpoint = True
        resp = client.get(ENDPOINT, headers={"Accept": "text/event-stream", **AUTH_HEADER})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# GET with session ID
# ---------------------------------------------------------------------------


def test_get_with_valid_session():
    """GET with valid session ID succeeds and returns session ID header."""
    # First create a session via initialize
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp.status_code == 200
    sid = resp.headers["mcp-session-id"]

    # Now GET with that session ID
    with patch("http_stream_transport.server.mcp_router.settings") as mock_settings:
        mock_settings.enable_sse_get_endpoint = True
        get_headers = {**GET_HEADERS, **AUTH_HEADER, "Mcp-Session-Id": sid}
        resp = client.get(ENDPOINT, headers=get_headers)
    assert resp.status_code == 200
    assert resp.headers["mcp-session-id"] == sid


def test_get_unknown_session_returns_404():
    """GET with unknown session ID returns 404."""
    with patch("http_stream_transport.server.mcp_router.settings") as mock_settings:
        mock_settings.enable_sse_get_endpoint = True
        get_headers = {
            **GET_HEADERS,
            **AUTH_HEADER,
            "Mcp-Session-Id": "nonexistent-session",
        }
        resp = client.get(ENDPOINT, headers=get_headers)
    assert resp.status_code == 404


def test_get_wrong_tenant_session_returns_403():
    """GET with session from different tenant returns 403."""
    # Create a session with tenant A
    headers_a = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers_a)
    assert resp.status_code == 200
    sid = resp.headers["mcp-session-id"]

    # Try to use tenant A's session with tenant B's token on GET
    with patch("http_stream_transport.server.mcp_router.settings") as mock_settings:
        mock_settings.enable_sse_get_endpoint = True
        get_headers = {
            **GET_HEADERS,
            "Authorization": f"Bearer {VALID_TOKEN_B}",
            "Mcp-Session-Id": sid,
        }
        resp = client.get(ENDPOINT, headers=get_headers)
    assert resp.status_code == 403
