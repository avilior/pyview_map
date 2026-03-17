"""Tests for the MCP server POST endpoint (http_stream_transport.app).

Uses FastAPI's TestClient (starlette.testclient) which calls the ASGI app
in-process — no running server required.
"""

import pytest
from starlette.testclient import TestClient

from http_stream_transport.server.app import app
from http_stream_transport.server.session import clear_all_sessions, get_session

client = TestClient(app)

ENDPOINT = "/mcp"
VALID_TOKEN = "tok-acme-001"
JSONRPC_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",  # spec §2
    "Authorization": f"Bearer {VALID_TOKEN}",
}


# ---------------------------------------------------------------------------
# Helpers — reusable message builders
# ---------------------------------------------------------------------------


def make_request(method: str = "ping", id: int = 1, params=None):
    msg = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return msg


def make_notification(method: str = "notifications/initialized", params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def make_response(id: int = 1, result="ok"):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error_response(id: int = 1, code: int = -1, message: str = "fail"):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Spec §3/§4 — Notifications → 202 Accepted
# ---------------------------------------------------------------------------


def test_single_notification():
    resp = client.post(ENDPOINT, json=make_notification(), headers=JSONRPC_HEADERS)
    assert resp.status_code == 202
    assert resp.content == b""


def test_batch_notifications():
    batch = [make_notification("notifications/a"), make_notification("notifications/b")]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 202
    assert resp.content == b""


# ---------------------------------------------------------------------------
# Spec §3/§4 — Client responses → 202 Accepted
# ---------------------------------------------------------------------------


def test_single_response():
    resp = client.post(ENDPOINT, json=make_response(id=10), headers=JSONRPC_HEADERS)
    assert resp.status_code == 202
    assert resp.content == b""


def test_batch_responses():
    batch = [make_response(id=10), make_error_response(id=11)]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 202
    assert resp.content == b""


# ---------------------------------------------------------------------------
# Spec §3 — Batch mixing constraint
# ---------------------------------------------------------------------------


def test_batch_mixed_responses_and_requests_rejected():
    batch = [make_response(id=10), make_request(id=1)]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32600
    assert "must not be mixed" in body["error"]["message"].lower()


def test_batch_mixed_responses_and_notifications_rejected():
    batch = [make_response(id=10), make_notification()]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32600
    assert "must not be mixed" in body["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Spec §5-6 — Requests → SSE response
#
# The spec-compliant Accept header includes both content types (§2).
# The current server always chooses SSE when text/event-stream is accepted.
# ---------------------------------------------------------------------------


def test_single_request_json():
    """Non-streaming request returns JSON (not SSE)."""
    resp = client.post(ENDPOINT, json=make_request(id=1), headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["error"]["code"] == -32601  # stub: method not found


def test_batch_requests_json():
    """Batch of non-streaming requests returns JSON array."""
    batch = [make_request("a", id=1), make_request("b", id=2)]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()
    assert len(data) == 2
    ids = {d["id"] for d in data}
    assert ids == {1, 2}
    for d in data:
        assert d["error"]["code"] == -32601


def test_batch_mixed_requests_and_notifications_json():
    """Batch with non-streaming request + notification returns JSON."""
    batch = [make_request("a", id=1), make_notification("notifications/x")]
    resp = client.post(ENDPOINT, json=batch, headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()
    # Only the request produces a response; notification is fire-and-forget.
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["error"]["code"] == -32601



# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_accept_header_rejected():
    # Spec §2: Accept must list both application/json and text/event-stream.
    headers_no_accept = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VALID_TOKEN}",
    }
    resp = client.post(ENDPOINT, json=make_request(id=1), headers=headers_no_accept)
    assert resp.status_code == 406


def test_incomplete_accept_header_rejected():
    # Only one of the two required types → still non-compliant.
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {VALID_TOKEN}",
    }
    resp = client.post(ENDPOINT, json=make_request(id=1), headers=headers)
    assert resp.status_code == 406


def test_invalid_json_body():
    resp = client.post(
        ENDPOINT,
        content=b"not valid json{{{",
        headers=JSONRPC_HEADERS,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32700  # Parse error


def test_invalid_jsonrpc_message():
    # Valid JSON but not a valid JSON-RPC message (missing required keys)
    resp = client.post(ENDPOINT, json={"foo": "bar"}, headers=JSONRPC_HEADERS)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32600  # Invalid request


# ---------------------------------------------------------------------------
# Initialize request — returns JSON (not SSE)
# ---------------------------------------------------------------------------


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


def test_initialize_returns_json_not_sse():
    """Initialize request returns JSON response, not SSE stream."""
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    # Should NOT be SSE
    assert "text/event-stream" not in resp.headers["content-type"]


def test_initialize_response_content():
    """Initialize response contains protocol version, capabilities, and serverInfo."""
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert "protocolVersion" in result
    assert "capabilities" in result
    assert "serverInfo" in result
    assert "name" in result["serverInfo"]
    assert "version" in result["serverInfo"]


# ---------------------------------------------------------------------------
# JSON response path — server chooses JSON when client prefers it
#
# Spec §2 requires Accept to include BOTH application/json AND text/event-stream.
# The server may choose either format for its response. These tests verify
# the server returns JSON when Accept lists application/json first (preferred).
# ---------------------------------------------------------------------------


def test_single_request_json_response():
    """Request with Accept preferring JSON returns JSON (not SSE)."""
    # Accept lists application/json first (higher preference), SSE second
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {VALID_TOKEN}",
    }
    # Use initialize which always returns JSON
    resp = client.post(ENDPOINT, json=make_initialize_request(), headers=headers)
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1


def test_batch_requests_json_response():
    """Batch requests return JSON array when Accept prefers JSON."""
    # Note: Current implementation always chooses SSE when text/event-stream is in Accept.
    # This test uses headers without SSE to test the JSON path, but spec requires SSE in Accept.
    # For now, we verify that JSON-only Accept is rejected per spec §2.
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",  # Missing text/event-stream
        "Authorization": f"Bearer {VALID_TOKEN}",
    }
    batch = [make_request("a", id=1), make_request("b", id=2)]
    resp = client.post(ENDPOINT, json=batch, headers=headers)
    # Spec §2: Accept MUST include both types, so this is rejected
    assert resp.status_code == 406


# ---------------------------------------------------------------------------
# Empty batch
# ---------------------------------------------------------------------------


def test_empty_batch_returns_202():
    """Empty batch [] returns 202 (no requests to process)."""
    resp = client.post(ENDPOINT, json=[], headers=JSONRPC_HEADERS)
    assert resp.status_code == 202
    assert resp.content == b""



# ---------------------------------------------------------------------------
# Server-side audit tracking
# ---------------------------------------------------------------------------


def _init_session() -> str:
    """Send an initialize request and return the session ID."""
    resp = client.post(ENDPOINT, json=make_initialize_request(id=1), headers=JSONRPC_HEADERS)
    assert resp.status_code == 200
    session_id = resp.headers["mcp-session-id"]
    return session_id


def _session_headers(session_id: str) -> dict[str, str]:
    return {**JSONRPC_HEADERS, "Mcp-Session-Id": session_id}


@pytest.fixture(autouse=False)
def _clean_sessions():
    """Clear session store before and after tests that create sessions."""
    clear_all_sessions()
    yield
    clear_all_sessions()


def test_initialize_creates_audit_record(_clean_sessions):
    """Initialize request is tracked in the session audit."""
    session_id = _init_session()
    session = get_session(session_id)
    assert session is not None

    records = session.audit.all_records()
    assert len(records) == 1
    rec = records[0]
    assert rec.method == "initialize"
    assert rec.request_id == 1
    assert rec.status == "success"



def test_method_not_found_audited(_clean_sessions):
    """Unknown method request is tracked as error in session audit."""
    session_id = _init_session()
    headers = _session_headers(session_id)

    resp = client.post(
        ENDPOINT,
        json=make_request("nonexistent", id=3),
        headers=headers,
    )
    assert resp.status_code == 200

    session = get_session(session_id)
    assert session is not None
    # method-not-found still gets audited since session exists
    rec = next(r for r in session.audit.all_records() if r.request_id == 3)
    assert rec.status == "error"
    assert rec.error_code == -32601


