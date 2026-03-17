"""Unit tests for JrpcAudit — the JSON-RPC request/response audit tracker."""

import time

from jrpc_common.jrpc_audit import JrpcAudit
from jrpc_common.jrpc_model import (
    JSONRPCError,
    JSONRPCErrorResponse,
    JSONRPCResponse,
    JsonRpcId,
)


def _make_success(rid: JsonRpcId, result: str = "ok") -> JSONRPCResponse:
    return JSONRPCResponse(id=rid, result=result)


def _make_error(rid: int, code: int = -32601, message: str = "Not found") -> JSONRPCErrorResponse:
    return JSONRPCErrorResponse(id=rid, error=JSONRPCError(code=code, message=message))


# ---------------------------------------------------------------------------
# Basic tracking
# ---------------------------------------------------------------------------


def test_track_request_creates_pending_record():
    audit = JrpcAudit()
    audit.track_request(1, "initialize")

    assert len(audit) == 1
    records = audit.pending()
    assert len(records) == 1
    assert records[0].request_id == 1
    assert records[0].method == "initialize"
    assert records[0].status == "pending"
    assert records[0].received_at is None


def test_track_success_response():
    audit = JrpcAudit()
    audit.track_request(1, "initialize")
    audit.track_response(1, _make_success(1))

    assert len(audit) == 1
    assert audit.pending() == []
    completed = audit.completed()
    assert len(completed) == 1
    assert completed[0].status == "success"
    assert completed[0].received_at is not None
    assert completed[0].error_code is None


def test_track_error_response():
    audit = JrpcAudit()
    audit.track_request(2, "tools/list")
    audit.track_response(2, _make_error(2, code=-32601, message="Method not found"))

    rec = audit.completed()[0]
    assert rec.status == "error"
    assert rec.error_code == -32601
    assert rec.error_message == "Method not found"


def test_track_response_for_unknown_id_is_ignored(caplog):
    """Response for an untracked id logs a warning and doesn't crash."""
    audit = JrpcAudit()
    audit.track_response(999, _make_success(999))

    assert len(audit) == 0
    assert "untracked request" in caplog.text.lower()


def test_track_request_with_explicit_sent_at():
    """track_request accepts an explicit sent_at timestamp."""
    audit = JrpcAudit()
    earlier = time.monotonic() - 10.0
    audit.track_request(1, "initialize", sent_at=earlier)

    rec = audit.pending()[0]
    assert rec.sent_at == earlier


def test_track_request_sent_at_defaults_to_now():
    """Without sent_at, the timestamp is close to now."""
    audit = JrpcAudit()
    before = time.monotonic()
    audit.track_request(1, "ping")
    after = time.monotonic()

    rec = audit.pending()[0]
    assert before <= rec.sent_at <= after


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def test_all_records():
    audit = JrpcAudit()
    audit.track_request(1, "a")
    audit.track_request(2, "b")
    audit.track_response(1, _make_success(1))

    assert len(audit.all_records()) == 2
    assert len(audit.pending()) == 1
    assert len(audit.completed()) == 1


def test_duration():
    audit = JrpcAudit()
    audit.track_request(1, "m")
    time.sleep(0.01)
    audit.track_response(1, _make_success(1))

    rec = audit.completed()[0]
    d = JrpcAudit.duration(rec)
    assert d is not None
    assert d >= 0.01


def test_duration_pending_is_none():
    audit = JrpcAudit()
    audit.track_request(1, "m")
    assert JrpcAudit.duration(audit.pending()[0]) is None


# ---------------------------------------------------------------------------
# String request ids
# ---------------------------------------------------------------------------


def test_string_request_id():
    audit = JrpcAudit()
    audit.track_request("abc-123", "ping")
    audit.track_response("abc-123", _make_success("abc-123"))

    assert len(audit.completed()) == 1
    assert audit.completed()[0].request_id == "abc-123"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def test_cleanup_removes_all_completed():
    audit = JrpcAudit()
    audit.track_request(1, "a")
    audit.track_request(2, "b")
    audit.track_response(1, _make_success(1))

    audit.cleanup()

    assert len(audit) == 1
    assert audit.pending()[0].request_id == 2


def test_cleanup_with_max_age():
    audit = JrpcAudit()
    audit.track_request(1, "a")
    audit.track_response(1, _make_success(1))
    # Manually backdate received_at so it's "old"
    audit._records[1].received_at = time.monotonic() - 100

    audit.track_request(2, "b")
    audit.track_response(2, _make_success(2))
    # This one is fresh

    audit.cleanup(max_age=50)

    # Only the old one should be removed
    assert len(audit) == 1
    assert audit.completed()[0].request_id == 2


def test_cleanup_preserves_pending():
    audit = JrpcAudit()
    audit.track_request(1, "a")
    audit.cleanup()
    assert len(audit) == 1


def test_clear_removes_everything():
    audit = JrpcAudit()
    audit.track_request(1, "a")
    audit.track_request(2, "b")
    audit.track_response(1, _make_success(1))

    audit.clear()
    assert len(audit) == 0


# ---------------------------------------------------------------------------
# Batch scenario
# ---------------------------------------------------------------------------


def test_batch_tracking():
    audit = JrpcAudit()
    audit.track_request(1, "tools/list")
    audit.track_request(2, "resources/list")
    audit.track_request(3, "prompts/list")

    assert len(audit.pending()) == 3

    audit.track_response(2, _make_success(2))
    audit.track_response(1, _make_error(1))
    audit.track_response(3, _make_success(3))

    assert len(audit.pending()) == 0
    assert len(audit.completed()) == 3

    statuses = {r.request_id: r.status for r in audit.all_records()}
    assert statuses == {1: "error", 2: "success", 3: "success"}
