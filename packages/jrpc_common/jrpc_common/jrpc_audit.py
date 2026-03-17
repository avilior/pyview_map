"""JRPC audit layer — tracks JSON-RPC request/response lifecycle."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from jrpc_common.jrpc_model import (
    JSONRPCErrorResponse,
    JSONRPCResponse,
    JsonRpcId,
)

LOG = logging.getLogger(__name__)


@dataclass
class JrpcAuditRecord:
    """A single tracked JSON-RPC request."""

    request_id: JsonRpcId
    method: str
    sent_at: float
    received_at: float | None = None
    status: str = "pending"
    error_code: int | None = None
    error_message: str | None = None


class JrpcAudit:
    """Tracks pending and completed JSON-RPC requests."""

    def __init__(self) -> None:
        self._records: dict[JsonRpcId, JrpcAuditRecord] = {}

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def track_request(self, request_id: JsonRpcId, method: str, *, sent_at: float | None = None) -> None:
        """Record a newly-sent request."""
        self._records[request_id] = JrpcAuditRecord(
            request_id=request_id,
            method=method,
            sent_at=sent_at if sent_at is not None else time.monotonic(),
        )

    def track_response(self, request_id: JsonRpcId, response: JSONRPCResponse | JSONRPCErrorResponse) -> None:
        """Match a response to its pending request and update the record."""
        record = self._records.get(request_id)
        if record is None:
            LOG.warning("Received response for untracked request id=%s", request_id)
            return

        record.received_at = time.monotonic()

        if isinstance(response, JSONRPCErrorResponse):
            record.status = "error"
            record.error_code = response.error.code
            record.error_message = response.error.message
        else:
            record.status = "success"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def pending(self) -> list[JrpcAuditRecord]:
        """Return records still waiting for a response."""
        return [r for r in self._records.values() if r.status == "pending"]

    def completed(self) -> list[JrpcAuditRecord]:
        """Return records that have received a response."""
        return [r for r in self._records.values() if r.status != "pending"]

    def all_records(self) -> list[JrpcAuditRecord]:
        """Return all tracked records."""
        return list(self._records.values())

    @staticmethod
    def duration(record: JrpcAuditRecord) -> float | None:
        """Compute round-trip time for a completed record."""
        if record.received_at is not None:
            return record.received_at - record.sent_at
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, max_age: float | None = None) -> None:
        """Remove completed records.

        If *max_age* is given (seconds), only completed records whose
        ``received_at`` is older than *max_age* seconds ago are removed.
        If *max_age* is ``None``, all completed records are removed.
        Pending records are never removed by this method.
        """
        now = time.monotonic()
        to_remove: list[JsonRpcId] = []
        for rid, rec in self._records.items():
            if rec.status == "pending":
                continue
            if max_age is None or (rec.received_at is not None and now - rec.received_at >= max_age):
                to_remove.append(rid)
        for rid in to_remove:
            del self._records[rid]

    def clear(self) -> None:
        """Remove all records (completed and pending)."""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
