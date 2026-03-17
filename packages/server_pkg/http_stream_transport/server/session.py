"""In-memory session store for MCP Streamable HTTP Transport.

Each session is tied to a tenant and tracked via the Mcp-Session-Id header.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from http_stream_transport.server.mock_tenant import Tenant
from jrpc_common.jrpc_audit import JrpcAudit


class Session(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    tenant: Tenant
    created_at: datetime
    active_streams: int = 0
    audit: JrpcAudit = Field(default_factory=JrpcAudit)


# In-memory store keyed by session_id.
_sessions: dict[str, Session] = {}


def create_session(tenant: Tenant) -> Session:
    """Create a new session for the given tenant and store it."""
    session_id = str(uuid.uuid4())
    session = Session(
        session_id=session_id,
        tenant=tenant,
        created_at=datetime.now(timezone.utc),
    )
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Look up a session by ID. Returns None if not found."""
    return _sessions.get(session_id)


def terminate_session(session_id: str) -> bool:
    """Remove a session. Returns True if it existed."""
    return _sessions.pop(session_id, None) is not None


def clear_all_sessions() -> None:
    """Remove all sessions. Used in tests for isolation."""
    _sessions.clear()
