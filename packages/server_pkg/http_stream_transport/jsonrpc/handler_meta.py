"""Handler introspection utilities for JRPCService.

Inspects handler function signatures at registration time to enable:
- Typed parameter extraction and validation via Pydantic
- Optional RequestContext / RequestInfo injection
- Sync handler support detection
- Return value validation
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter, create_model

from jrpc_common.jrpc_model import JsonRpcId


@dataclass(frozen=True)
class RequestInfo:
    """Minimal request metadata injected into handlers that declare an ``info: RequestInfo`` parameter."""

    id: JsonRpcId
    method: str


@dataclass(frozen=True)
class HandlerMeta:
    """Metadata extracted from a handler function at registration time."""

    name: str
    is_async: bool
    wants_ctx: bool
    wants_request_info: bool
    param_model: type[BaseModel] | None  # Pydantic model built from typed params, None if no params
    return_type: type | None
    has_var_keyword: bool  # True when handler uses **kwargs


@dataclass(frozen=True)
class MethodRecord:
    """Full registration record for a JSON-RPC method."""

    name: str
    kind: str  # "request" or "notification"
    handler_meta: HandlerMeta
    func: Callable[..., Any]
    param_schema: dict[str, Any] | None
    return_schema: dict[str, Any] | None
    docstring: str | None
    module: str
    qualname: str
    is_async: bool


def _return_type_schema(return_type: type | None) -> dict[str, Any] | None:
    """Build a JSON Schema dict for a handler's return type, or None."""
    if return_type is None or return_type is type(None):
        return None
    try:
        adapter = TypeAdapter(return_type)
        return adapter.json_schema()
    except Exception:
        return {"type": str(return_type)}


def build_method_record(jrpc_name: str, fn: Any, meta: HandlerMeta, *, kind: str) -> MethodRecord:
    """Create a :class:`MethodRecord` from a handler function and its introspected metadata."""
    param_schema = meta.param_model.model_json_schema() if meta.param_model else None
    return_schema = _return_type_schema(meta.return_type)
    return MethodRecord(
        name=jrpc_name,
        kind=kind,
        handler_meta=meta,
        func=fn,
        param_schema=param_schema,
        return_schema=return_schema,
        docstring=fn.__doc__,
        module=fn.__module__,
        qualname=fn.__qualname__,
        is_async=meta.is_async,
    )


def inspect_handler(fn: Any) -> HandlerMeta:
    """Inspect a handler function and extract registration metadata.

    Uses ``inspect.signature`` and ``typing.get_type_hints`` to determine
    parameter types, special injections (ctx, info), and return type.
    """
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    # Avoid circular import — compare by name rather than importing RequestContext
    from http_stream_transport.jsonrpc.jrpc_service import RequestContext

    wants_ctx = False
    wants_request_info = False
    has_var_keyword = False
    fields: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        annotation = hints.get(param_name, Any)

        # Detect special injectable parameters
        if annotation is RequestContext or (isinstance(annotation, type) and issubclass(annotation, RequestContext)):
            wants_ctx = True
            continue

        if annotation is RequestInfo or (isinstance(annotation, type) and issubclass(annotation, RequestInfo)):
            wants_request_info = True
            continue

        # Detect **kwargs
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue

        # Skip *args
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            continue

        # Build field for Pydantic model
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (annotation, default)

    # Build Pydantic param model if there are typed fields
    param_model = None
    if fields:
        model_name = f"{fn.__name__}_Params"
        param_model = create_model(model_name, **fields)

    return_type = hints.get("return")

    return HandlerMeta(
        name=fn.__name__,
        is_async=inspect.iscoroutinefunction(fn),
        wants_ctx=wants_ctx,
        wants_request_info=wants_request_info,
        param_model=param_model,
        return_type=return_type,
        has_var_keyword=has_var_keyword,
    )


def validate_return(value: Any, expected_type: type) -> None:
    """Validate a handler's return value against its declared return type.

    Raises ``TypeError`` if the value does not match.
    """
    if expected_type is Any or expected_type is type(None):
        return

    # SSEQueue (asyncio.Queue) — skip validation
    if isinstance(value, asyncio.Queue):
        return

    origin = get_origin(expected_type)

    # For generic types like dict[str, Any], check against the origin
    if origin is not None:
        if not isinstance(value, origin):
            raise TypeError(f"Expected {expected_type}, got {type(value).__name__}")
        return

    # Simple type check
    if isinstance(expected_type, type) and not isinstance(value, expected_type):
        raise TypeError(f"Expected {expected_type.__name__}, got {type(value).__name__}")
