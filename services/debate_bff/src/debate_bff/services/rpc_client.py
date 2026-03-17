"""Thin wrapper around the http_stream_client SDK for backend communication."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from jrpc_common.jrpc_model import (
    JSONRPCMessage,
    JSONRPCRequest,
)
from http_stream_client.jsonrpc.client_sdk import ClientRPC

LOG = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.environ.get("DEBATE_BACKEND_URL", "http://localhost:8000")
DEFAULT_AUTH_TOKEN = "tok-acme-001"


class ChatRPCClient:
    """Manages a single MCP session to the backend."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        auth_token: str = DEFAULT_AUTH_TOKEN,
    ) -> None:
        self.base_url = base_url
        self.auth_token = auth_token
        self._rpc: ClientRPC | None = ClientRPC(base_url=self.base_url, auth_token=self.auth_token)
        self._session_id: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._rpc is not None and self._rpc._initialized

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def connect(self) -> str | None:
        """Initialize the MCP session (health check + initialize + initialized).

        Returns the session ID on success.
        """

        if self._rpc is None:
            raise RuntimeError("Not connected — call connect() first")

        LOG.info("Connecting to backend at %s", self.base_url)
        await self._rpc.start()
        self._session_id = self._rpc._session_id
        LOG.info("Connected — session_id=%s", self._session_id)
        return self._session_id

    async def send_request(
        self,
        method: str,
        params: dict | None = None,
    ) -> AsyncGenerator[JSONRPCMessage]:
        """Send a JSON-RPC request and yield streaming responses.

        Yields JSONRPCNotification for intermediate streaming events
        and JSONRPCResponse/JSONRPCErrorResponse for the final result.
        """
        if self._rpc is None:
            raise RuntimeError("Not connected — call connect() first")

        request = JSONRPCRequest(method=method, params=params or {})
        async for msg in self._rpc.send_request(request):
            yield msg

    async def disconnect(self) -> None:
        """Close the MCP session."""
        if self._rpc is not None:
            LOG.info("Disconnecting from backend")
            await self._rpc.close()
            self._rpc = None
            self._session_id = None
