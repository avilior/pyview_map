"""Tests for tenant authentication and session management.

Each test calls clear_all_sessions() for isolation.
"""

import pytest
from starlette.testclient import TestClient

from http_stream_transport.server.app import app
from http_stream_transport.server.mock_tenant import get_tenant_by_token
from http_stream_transport.server.session import clear_all_sessions

client = TestClient(app)

ENDPOINT = "/mcp"
POST_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
GET_HEADERS = {"Accept": "text/event-stream"}

VALID_TOKEN = "tok-acme-001"
VALID_TOKEN_B = "tok-globex-002"


def make_notification(method: str = "notifications/initialized"):
    return {"jsonrpc": "2.0", "method": method}


def make_request(method: str = "ping", id: int = 1):
    return {"jsonrpc": "2.0", "method": method, "id": id}


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
# Tenant lookup
# ---------------------------------------------------------------------------


def test_valid_token_returns_tenant():
    tenant = get_tenant_by_token(VALID_TOKEN)
    assert tenant is not None
    assert tenant.tenant_id == "t-acme"


def test_invalid_token_returns_none():
    assert get_tenant_by_token("bad-token") is None


# ---------------------------------------------------------------------------
# Auth enforcement — auth is always required
# ---------------------------------------------------------------------------


def test_post_no_token_returns_401():
    resp = client.post(ENDPOINT, json=make_notification(), headers=POST_HEADERS)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_post_bad_token_returns_401():
    headers = {**POST_HEADERS, "Authorization": "Bearer bad-token"}
    resp = client.post(ENDPOINT, json=make_notification(), headers=headers)
    assert resp.status_code == 401


def test_get_no_token_returns_401():
    resp = client.get(ENDPOINT, headers=GET_HEADERS)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# Session creation — initialize request creates Mcp-Session-Id
# ---------------------------------------------------------------------------


def test_initialize_creates_session():
    """Initialize request creates a session and returns Mcp-Session-Id."""
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers
    sid = resp.headers["mcp-session-id"]
    assert len(sid) > 0


def test_notification_without_session_has_no_session_id():
    """Notification without prior initialize has no session ID."""
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_notification(), headers=headers)
    assert resp.status_code == 202
    # No session created without initialize
    assert "mcp-session-id" not in resp.headers


# ---------------------------------------------------------------------------
# Session reuse — same token + session ID reuses the session
# ---------------------------------------------------------------------------


def test_session_reuse():
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}

    # Initialize creates a session
    resp1 = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp1.status_code == 200
    sid = resp1.headers["mcp-session-id"]

    # Subsequent request with the same session ID reuses it
    headers["Mcp-Session-Id"] = sid
    resp2 = client.post(ENDPOINT, json=make_notification(), headers=headers)
    assert resp2.status_code == 202
    assert resp2.headers["mcp-session-id"] == sid


# ---------------------------------------------------------------------------
# Unknown session — Mcp-Session-Id with nonexistent ID → 404
# ---------------------------------------------------------------------------


def test_unknown_session_returns_404():
    headers = {
        **POST_HEADERS,
        "Authorization": f"Bearer {VALID_TOKEN}",
        "Mcp-Session-Id": "nonexistent-session-id",
    }
    resp = client.post(ENDPOINT, json=make_notification(), headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation — session from tenant A rejected with tenant B's token
# ---------------------------------------------------------------------------


def test_tenant_isolation():
    # Create a session with tenant A via initialize
    headers_a = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers_a)
    assert resp.status_code == 200
    sid = resp.headers["mcp-session-id"]

    # Try to use tenant A's session with tenant B's token
    headers_b = {
        **POST_HEADERS,
        "Authorization": f"Bearer {VALID_TOKEN_B}",
        "Mcp-Session-Id": sid,
    }
    resp = client.post(ENDPOINT, json=make_notification(), headers=headers_b)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Session ID format — all chars in visible ASCII range (0x21–0x7E)
# ---------------------------------------------------------------------------


def test_session_id_format():
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp.status_code == 200
    sid = resp.headers["mcp-session-id"]
    for ch in sid:
        assert 0x21 <= ord(ch) <= 0x7E, f"char {ch!r} (0x{ord(ch):02X}) outside visible ASCII"


# ---------------------------------------------------------------------------
# Non-initialize requests don't create sessions
# ---------------------------------------------------------------------------


def test_non_initialize_request_no_session():
    """Non-initialize request without session ID doesn't create a session."""
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    # Send a regular request (not initialize)
    resp = client.post(ENDPOINT, json=make_request("ping", id=1), headers=headers)
    assert resp.status_code == 200
    # No session should be created
    assert "mcp-session-id" not in resp.headers


# ---------------------------------------------------------------------------
# Initialize response content
# ---------------------------------------------------------------------------


def test_initialize_response_has_required_fields():
    """Initialize response includes protocolVersion, capabilities, and serverInfo."""
    headers = {**POST_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"}
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    result = body["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert "capabilities" in result
    assert "serverInfo" in result
    assert result["serverInfo"]["name"] == "http_stream_transport"
    assert "version" in result["serverInfo"]
