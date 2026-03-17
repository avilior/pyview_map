# ---------------------------------------------------------------------------
# JSON-RPC Service
#
# Routes incoming JSON-RPC requests to registered method handlers.
#
# Handlers are plain functions with typed parameters.  At registration time
# the service introspects the handler's signature and builds a Pydantic
# model for automatic parameter validation.  Special parameters (ctx, info)
# are injected by the framework; sync handlers are run in a thread.
#
# Return types per JSON-RPC 2.0:
#   - JSONRPCResponse      → request handled successfully (id + result)
#   - JSONRPCErrorResponse → request failed (id + error)
#
# MCP SSE note (spec §6):
#   During request processing the server MAY emit intermediate messages
#   (notifications or server-to-client requests) on the SSE stream before
#   the final response.  These are a transport-layer concern and are NOT
#   part of dispatch_request's return value.
# ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from pydantic import ValidationError

from jrpc_common.jrpc_model import (
    JSONRPCErrorResponse,
    JSONRPCError,
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPCNotification,
    JSONRPCResponse,
    JSONRPCRequest,
)
from http_stream_transport.jsonrpc.handler_meta import (
    HandlerMeta,
    MethodRecord,
    RequestInfo,
    build_method_record,
    inspect_handler,
    validate_return,
)

if TYPE_CHECKING:
    from http_stream_transport.server.mock_tenant import Tenant
    from http_stream_transport.server.session import Session

LOG = logging.getLogger(__name__)

SSEQueue = asyncio.Queue[JSONRPCNotification | JSONRPCResponse | JSONRPCErrorResponse]


@dataclass
class RequestContext:
    """Context for processing JSON-RPC requests.

    Holds tenant and session information, allowing handlers to create
    or access sessions as needed.
    """

    tenant: Tenant
    session: Session | None = field(default=None)

    @property
    def session_id(self) -> str | None:
        """Return the session ID if a session exists."""
        return self.session.session_id if self.session else None

    def create_session(self) -> Session:
        """Create a new session for the tenant and store it in context."""
        from http_stream_transport.server.session import create_session

        self.session = create_session(self.tenant)
        return self.session


# Internal handler type — the wrapper signature used by dispatch_request/dispatch_notification.
RequestHandler = Callable[
    [JSONRPCRequest, RequestContext],
    Awaitable[JSONRPCResponse | JSONRPCErrorResponse | SSEQueue],
]
NotificationHandler = Callable[[JSONRPCNotification, RequestContext], Awaitable[None]]


class JRPCService:
    """Registry-based JSON-RPC method dispatcher.

    Handlers register via decorators and are looked up by method name at
    dispatch time.  Handler signatures are introspected at registration to
    enable typed parameter injection, validation, and sync support.
    """

    def __init__(self) -> None:
        self._request_handlers: dict[str, RequestHandler] = {}
        self._notification_handlers: dict[str, NotificationHandler] = {}
        self._method_records: dict[str, MethodRecord] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Built-in handlers
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the built-in initialize / initialized handlers."""
        meta_init = inspect_handler(self._initialize_method)
        self._request_handlers["initialize"] = self._build_request_wrapper(
            self._initialize_method, meta_init,
        )
        self._method_records["initialize"] = build_method_record(
            "initialize", self._initialize_method, meta_init, kind="request",
        )

        meta_notif = inspect_handler(self._initialized_notification)
        self._notification_handlers["notifications/initialized"] = self._build_notification_wrapper(
            self._initialized_notification, meta_notif,
        )
        self._method_records["notifications/initialized"] = build_method_record(
            "notifications/initialized", self._initialized_notification, meta_notif, kind="notification",
        )

    async def _initialize_method(self, ctx: RequestContext) -> dict:
        """Handle the JSON-RPC initialization request.

        Creates a new session for the tenant and returns the server's protocol
        version, capabilities, and server info per the MCP lifecycle spec.
        """
        ctx.create_session()
        LOG.info("Created session %s for tenant %s", ctx.session_id, ctx.tenant.tenant_id)

        return {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "serverInfo": {
                "name": "http_stream_transport",
                "version": "0.1.0",
            },
        }

    async def _initialized_notification(self, ctx: RequestContext) -> None:
        """Handle the ``notifications/initialized`` notification from the client."""
        LOG.info(
            "Client initialized — tenant=%s session=%s",
            ctx.tenant.tenant_id,
            ctx.session_id,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def registered_methods(self) -> dict[str, MethodRecord]:
        """Return all registered method records, keyed by JSON-RPC method name."""
        return dict(sorted(self._method_records.items()))

    # ------------------------------------------------------------------
    # Decorator registration
    # ------------------------------------------------------------------

    def method(self, name: str | None = None) -> Any:
        """Decorator to mark an instance method for deferred JSON-RPC registration.

        When applied to a class method (one whose first parameter is ``self``),
        the handler is **not** registered immediately.  Instead, metadata is
        stashed on the function so that :meth:`register_instance` can bind and
        register it later.

        When applied to a plain function (no ``self`` parameter), it registers
        immediately — behaving identically to :meth:`request`.

        Usage::

            class Calc:
                @jrpc_service.method(name="Calculator.add")
                def add(self, a: int, b: int) -> int: ...

                @jrpc_service.method()
                def subtract(self, a: int, b: int) -> int: ...
        """

        def decorator(fn: Any) -> Any:
            resolved = name or fn.__name__
            sig = inspect.signature(fn)
            params = list(sig.parameters)
            if params and params[0] == "self":
                # Defer registration — stash the method name for register_instance
                fn._jrpc_method_name = resolved
            else:
                # Plain function — register immediately like request()
                meta = inspect_handler(fn)
                self._request_handlers[resolved] = self._build_request_wrapper(fn, meta)
                self._method_records[resolved] = build_method_record(resolved, fn, meta, kind="request")
            return fn

        return decorator

    def register_instance(self, instance: Any) -> None:
        """Bind and register all ``@method()``-decorated methods from *instance*.

        Iterates over the instance's class, finds attributes carrying the
        ``_jrpc_method_name`` marker set by :meth:`method`, binds them to the
        instance, and registers each as a request handler.
        """
        for attr_name in dir(type(instance)):
            unbound = getattr(type(instance), attr_name, None)
            jrpc_name = getattr(unbound, "_jrpc_method_name", None)
            if jrpc_name is None:
                continue
            bound = getattr(instance, attr_name)
            meta = inspect_handler(bound)
            self._request_handlers[jrpc_name] = self._build_request_wrapper(bound, meta)
            self._method_records[jrpc_name] = build_method_record(jrpc_name, bound, meta, kind="request")

    def request(self, method: str | Callable | None = None) -> Any:
        """Decorator to register a request handler.

        Usage::

            @jrpc_service.request("echo")
            async def echo(**kwargs) -> dict: ...

            @jrpc_service.request
            async def echo(**kwargs) -> dict: ...   # method name = "echo"
        """

        def decorator(fn: Any) -> Any:
            meta = inspect_handler(fn)
            resolved = method_name or meta.name
            self._request_handlers[resolved] = self._build_request_wrapper(fn, meta)
            self._method_records[resolved] = build_method_record(resolved, fn, meta, kind="request")
            return fn

        # @jrpc_service.request  (no parentheses — method is the function itself)
        if callable(method):
            method_name: str | None = None
            return decorator(method)

        # @jrpc_service.request("name")
        method_name = method
        return decorator

    def notification(self, method: str | Callable | None = None) -> Any:
        """Decorator to register a notification handler.

        Usage::

            @jrpc_service.notification("notifications/progress")
            async def on_progress(ctx: RequestContext) -> None: ...

            @jrpc_service.notification
            async def on_progress(ctx: RequestContext) -> None: ...
        """

        def decorator(fn: Any) -> Any:
            meta = inspect_handler(fn)
            resolved = method_name or meta.name
            self._notification_handlers[resolved] = self._build_notification_wrapper(fn, meta)
            self._method_records[resolved] = build_method_record(resolved, fn, meta, kind="notification")
            return fn

        if callable(method):
            method_name: str | None = None
            return decorator(method)

        method_name = method
        return decorator

    # ------------------------------------------------------------------
    # Wrapper builders
    # ------------------------------------------------------------------

    def _build_request_wrapper(self, fn: Any, meta: HandlerMeta) -> RequestHandler:
        """Build an async wrapper adapting a typed handler to the internal dispatch interface."""

        async def wrapper(rpc: JSONRPCRequest, ctx: RequestContext) -> JSONRPCResponse | JSONRPCErrorResponse | SSEQueue:
            # 1. Build kwargs from params
            kwargs: dict[str, Any] = {}
            raw_params = rpc.params if isinstance(rpc.params, dict) else {}

            if meta.param_model is not None:
                try:
                    validated = meta.param_model.model_validate(raw_params or {})
                    kwargs = validated.model_dump()
                except ValidationError as e:
                    return JSONRPCErrorResponse(
                        id=rpc.id,
                        error=JSONRPCError(code=JSONRPC_INVALID_PARAMS, message=str(e)),
                    )
            elif meta.has_var_keyword:
                kwargs = dict(raw_params) if raw_params else {}

            # 2. Inject special parameters
            if meta.wants_ctx:
                kwargs["ctx"] = ctx
            if meta.wants_request_info and rpc.id is not None:
                kwargs["info"] = RequestInfo(id=rpc.id, method=rpc.method)

            # 3. Call handler
            try:
                if meta.is_async:
                    result = await fn(**kwargs)
                else:
                    result = await asyncio.to_thread(fn, **kwargs)
            except Exception as e:
                LOG.exception("Handler %s raised", meta.name)
                return JSONRPCErrorResponse(
                    id=rpc.id,
                    error=JSONRPCError(code=JSONRPC_INTERNAL_ERROR, message=str(e)),
                )

            # 4. SSEQueue — pass through
            if isinstance(result, asyncio.Queue):
                return result

            # 5. Validate return value
            if meta.return_type is not None:
                try:
                    validate_return(result, meta.return_type)
                except TypeError as e:
                    LOG.error("Return validation failed for %s: %s", meta.name, e)
                    return JSONRPCErrorResponse(
                        id=rpc.id,
                        error=JSONRPCError(code=JSONRPC_INTERNAL_ERROR, message=str(e)),
                    )

            # 6. Wrap in JSONRPCResponse
            return JSONRPCResponse(id=rpc.id, result=result)

        return wrapper

    def _build_notification_wrapper(self, fn: Any, meta: HandlerMeta) -> NotificationHandler:
        """Build an async wrapper for a notification handler."""

        async def wrapper(notification: JSONRPCNotification, ctx: RequestContext) -> None:
            kwargs: dict[str, Any] = {}
            raw_params = notification.params if isinstance(notification.params, dict) else {}

            if meta.param_model is not None:
                try:
                    validated = meta.param_model.model_validate(raw_params or {})
                    kwargs = validated.model_dump()
                except ValidationError:
                    LOG.warning("Invalid params for notification %s", notification.method)
                    return
            elif meta.has_var_keyword:
                kwargs = dict(raw_params) if raw_params else {}

            if meta.wants_ctx:
                kwargs["ctx"] = ctx

            if meta.is_async:
                await fn(**kwargs)
            else:
                await asyncio.to_thread(fn, **kwargs)

        return wrapper

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch_request(
        self,
        rpc: JSONRPCRequest,
        ctx: RequestContext,
    ) -> JSONRPCResponse | JSONRPCErrorResponse | SSEQueue:
        """Route a JSON-RPC request to the appropriate registered handler."""
        assert rpc.id is not None, "JSON-RPC requests must have an id"
        LOG.info(f"Handling request [{rpc.id}]: {rpc.method}")
        handler = self._request_handlers.get(rpc.method)
        if handler is None:
            LOG.warning("Unhandled request: %s", rpc.method)
            error_result = JSONRPCErrorResponse(
                id=rpc.id,
                error=JSONRPCError(
                    code=JSONRPC_METHOD_NOT_FOUND,
                    message=f"Method not found or implemented: {rpc.method}",
                ),
            )
            if ctx.session is not None:
                ctx.session.audit.track_request(rpc.id, rpc.method)
                ctx.session.audit.track_response(rpc.id, error_result)
            return error_result

        start = time.monotonic()
        result = await handler(rpc, ctx)

        if ctx.session is not None:
            ctx.session.audit.track_request(rpc.id, rpc.method, sent_at=start)
            if not isinstance(result, asyncio.Queue):
                ctx.session.audit.track_response(rpc.id, result)

        return result

    async def dispatch_notification(self, notification: JSONRPCNotification, ctx: RequestContext) -> None:
        """Route a JSON-RPC notification to the appropriate registered handler."""
        handler = self._notification_handlers.get(notification.method)
        if handler is None:
            LOG.warning("Unhandled notification: %s", notification.method)
            return
        await handler(notification, ctx)


# ---------------------------------------------------------------------------
# Module-level registry
# ---------------------------------------------------------------------------

jrpc_service = JRPCService()


# Module-level convenience functions

async def dispatch_request(
    rpc: JSONRPCRequest,
    ctx: RequestContext,
) -> JSONRPCResponse | JSONRPCErrorResponse | SSEQueue:
    return await jrpc_service.dispatch_request(rpc, ctx)


async def dispatch_notification(notification: JSONRPCNotification, ctx: RequestContext) -> None:
    await jrpc_service.dispatch_notification(notification, ctx)


