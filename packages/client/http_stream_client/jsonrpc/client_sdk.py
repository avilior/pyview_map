"""MCP client SDK — single-session RPC client.

Each ``ClientRPC`` instance represents one MCP session.  It owns a long-lived
``httpx.AsyncClient`` created on ``start()`` and torn down on ``close()``.

Lifecycle (per ``specification/lifecycle.md``):
    health check → ``initialize`` request → ``initialized`` notification
"""

from __future__ import annotations

import json
import logging
from typing import Any, Self

import httpx
from collections.abc import AsyncGenerator, Generator

from jrpc_common.jrpc_model import (
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    parse_jsonrpc,
)
from jrpc_common.jrpc_audit import JrpcAudit

LOG = logging.getLogger(__name__)

ACCEPT_HEADER = "application/json, text/event-stream"
MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_SESSION_ID_HEADER = "Mcp-Session-Id"


class BearerAuth(httpx.Auth):
    """Bearer token authentication for httpx."""

    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class ClientRPC:
    """A single RPC session backed by one ``httpx.AsyncClient``."""

    def __init__(self, *, base_url: str, auth_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = BearerAuth(auth_token)  # the Tenant Auth token
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None
        self._request_id: int = 0  # JSONRPC request id
        self._initialized: bool = False
        self.audit = JrpcAudit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the HTTP client and run the MCP initialization handshake."""
        LOG.info("Starting MCP client session")
        self._client = httpx.AsyncClient(
            timeout=None,
            auth=self.auth_token,
            headers={"Accept": ACCEPT_HEADER},
            event_hooks={"request": [self._inject_session_id]},
        )
        LOG.info("Created HTTP client")
        r = await self.health()
        LOG.info(f"Health check response: {r}")
        r = await self.initialize()
        self._initialized = True
        LOG.info(f"MCP client session initialized: {r}")

    async def close(self) -> None:
        """Shut down the HTTP client."""
        if self._client is None:
            return
        pending = self.audit.pending()
        if pending:
            LOG.warning(
                "Closing with %d pending request(s): %s",
                len(pending),
                [(r.request_id, r.method) for r in pending],
            )
        self.audit.clear()
        await self._client.aclose()
        self._client = None
        self._initialized = False

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # MCP lifecycle methods
    # ------------------------------------------------------------------

    async def health(self) -> dict:
        """``GET /health`` — quick liveness check (no auth)."""
        assert self._client is not None, "call start() first"
        response = await self._client.get(f"{self.base_url}/health", auth=None)
        response.raise_for_status()
        return response.json()

    async def initialize(self) -> JSONRPCMessage:
        """Run the MCP initialization handshake.

        1. Send an ``initialize`` request with protocol version and client info.
        2. Send a ``notifications/initialized`` notification.
        3. Return the server's initialization response.
        """
        initialize_jrpc = JSONRPCRequest(
            method="initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "http_stream_client",
                    "version": "0.1.0",
                },
            },
        )

        # resp = await self.send_request(initialize_jrpc)
        async for resp in self.send_request(initialize_jrpc):
            LOG.info(f"initialize response: {resp}")
            # TODO do something with the response

        # Upon successful initialization, a session_id is returned
        LOG.info("MCP client session initialized: NEED TO GET IT ????")
        # TODO extract the session_id and put it the class.

        # After successful initialization, the client MUST send an initialized notification to indicate it is ready to
        # begin normal operations:
        notification_initialized_jrpc = JSONRPCNotification(method="notifications/initialized")
        await self.send_notification(notification_jrpc=notification_initialized_jrpc)
        return resp

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def send_request(self, request: JSONRPCRequest | list[JSONRPCRequest], ) -> AsyncGenerator[JSONRPCMessage]:
        """Send a single or batch JSON-RPC request and return the parsed response(s)."""
        assert self._client is not None, "call start() first"

        if isinstance(request, list):
            is_batch = True
            for req in request:
                if req.id is None:
                    req.id = self._next_id()
            for req in request:
                assert req.id is not None      # This can never happen because of the loop above, but mypy doesn't know that.
                self.audit.track_request(req.id, req.method)

            payload = [r.model_dump(exclude_none=True) for r in request]

        else:
            is_batch = False
            if request.id is None:
                request.id = self._next_id()
            self.audit.track_request(request.id, request.method)
            payload = request.model_dump(exclude_none=True)

        async with self._client.stream("POST", f"{self.base_url}/mcp", json=payload,) as response:

            response.raise_for_status()
            self._update_session_id(response)

            if response.status_code == 202:
                raise RuntimeError(f"Expected a response for request, got {response.status_code}")

            content_type = response.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                # messages: list[JSONRPCMessage] = []
                got_message = False
                async for msg in self._parse_sse_stream(response):
                    got_message = True
                    LOG.debug("SSE event: %s", msg)
                    if isinstance(msg, (JSONRPCResponse, JSONRPCErrorResponse)) and msg.id is not None:
                        self.audit.track_response(msg.id, msg)
                    yield msg

                if not got_message:
                    raise RuntimeError("SSE stream ended with no messages")

                # if is_batch:
                #     return messages
                # assert isinstance(messages[-1], (JSONRPCResponse, JSONRPCErrorResponse))
                # return messages[-1]
                return

            if "application/json" in content_type:
                data = json.loads(await response.aread())
                if is_batch:
                    assert isinstance(data, list)
                    for item in data:
                        parsed_item = parse_jsonrpc(item)
                        if (
                            isinstance(parsed_item, (JSONRPCResponse, JSONRPCErrorResponse))
                            and parsed_item.id is not None
                        ):
                            self.audit.track_response(parsed_item.id, parsed_item)
                        yield parsed_item
                    return
                parsed = parse_jsonrpc(data)
                assert isinstance(parsed, (JSONRPCResponse, JSONRPCErrorResponse))
                if parsed.id is not None:
                    self.audit.track_response(parsed.id, parsed)
                yield parsed
                return

            raise ValueError(f"Unexpected content type: {content_type}")

    async def send_notification(self, *, notification_jrpc: JSONRPCNotification) -> None:
        """Send a JSON-RPC notification (expects 202 Accepted)."""

        # TODO: What about batch notifications?

        assert self._client is not None, "call start() first"

        response = await self._client.post(f"{self.base_url}/mcp", json=notification_jrpc.model_dump(exclude_none=True),)
        response.raise_for_status()
        self._update_session_id(response)

    async def open_sse_stream(self) -> None:
        """``GET /mcp`` SSE stream for server-initiated messages (stub)."""
        raise NotImplementedError("open_sse_stream is not yet implemented")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _parse_sse_stream(response: httpx.Response) -> AsyncGenerator[JSONRPCMessage]:
        """Parse an SSE stream, yielding a JSONRPCMessage for each event whose data is valid JSON-RPC."""
        data_lines: list[str] = []

        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data_lines.append(line[6:])
            elif line.startswith("data:"):
                data_lines.append(line[5:])
            elif line == "":
                if data_lines:
                    payload = "\n".join(data_lines)
                    parsed = json.loads(payload)
                    if isinstance(parsed, list):
                        for item in parsed:
                            yield parse_jsonrpc(item)
                    else:
                        yield parse_jsonrpc(parsed)
                    data_lines = []

        # Flush trailing data if the stream closed without a final blank line.
        if data_lines:
            payload = "\n".join(data_lines)
            parsed = json.loads(payload)
            if isinstance(parsed, list):
                for item in parsed:
                    yield parse_jsonrpc(item)
            else:
                yield parse_jsonrpc(parsed)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _inject_session_id(self, request: httpx.Request) -> None:
        """Event hook to add session ID header to requests."""
        if self._session_id is not None:
            request.headers[MCP_SESSION_ID_HEADER] = self._session_id

    def _update_session_id(self, response: httpx.Response) -> None:
        sid = response.headers.get(MCP_SESSION_ID_HEADER)

        if sid is not None:
            sid = sid.strip()
            if sid == "":
                raise ValueError("Empty Mcp-Session-Id header")
            # If we already have a session id, it must match the header
            if self._session_id is not None:
                if self._session_id != sid:
                    LOG.error(
                        "Session ID mismatch: existing=%r header=%r",
                        self._session_id,
                        sid,
                    )
                    raise RuntimeError(f"Session ID changed from {self._session_id!r} to {sid!r}")
                # matching session id: nothing to do
                return
            # No existing session id: accept the header (can happen during initialization)
            LOG.debug("Setting new session id: %s", sid)
            self._session_id = sid
        else:
            # No session-id header
            if response.status_code == 404:
                LOG.debug("Clearing session id due to 404 response")
                self._session_id = None
            else:
                # TODO is this what we should do if we receive an empty session id.
                LOG.debug(
                    "No Mcp-Session-Id header present (status=%s); leaving session unchanged",
                    response.status_code,
                )
