"""Unit tests for handler_meta — introspection, param model building, return validation."""

import asyncio

from http_stream_transport.jsonrpc.handler_meta import (
    MethodRecord,
    RequestInfo,
    build_method_record,
    inspect_handler,
    validate_return,
)
from http_stream_transport.jsonrpc.jrpc_service import RequestContext


# ---------------------------------------------------------------------------
# inspect_handler tests
# ---------------------------------------------------------------------------


def test_inspect_no_params():
    async def handler():
        return {}

    meta = inspect_handler(handler)
    assert meta.name == "handler"
    assert meta.is_async is True
    assert meta.wants_ctx is False
    assert meta.wants_request_info is False
    assert meta.param_model is None
    assert meta.has_var_keyword is False


def test_inspect_typed_params():
    async def handler(name: str, count: int = 3):
        pass

    meta = inspect_handler(handler)
    assert meta.param_model is not None
    assert "name" in meta.param_model.model_fields
    assert "count" in meta.param_model.model_fields


def test_inspect_with_ctx():
    async def handler(ctx: RequestContext, name: str = "x"):
        pass

    meta = inspect_handler(handler)
    assert meta.wants_ctx is True
    # ctx should not be in the param model
    assert meta.param_model is not None
    assert "ctx" not in meta.param_model.model_fields
    assert "name" in meta.param_model.model_fields


def test_inspect_with_request_info():
    async def handler(info: RequestInfo, count: int = 1):
        pass

    meta = inspect_handler(handler)
    assert meta.wants_request_info is True
    assert meta.param_model is not None
    assert "info" not in meta.param_model.model_fields
    assert "count" in meta.param_model.model_fields


def test_inspect_var_keyword():
    async def handler(**kwargs):
        pass

    meta = inspect_handler(handler)
    assert meta.has_var_keyword is True
    assert meta.param_model is None


def test_inspect_sync_function():
    def handler(x: int = 1):
        return x

    meta = inspect_handler(handler)
    assert meta.is_async is False
    assert meta.param_model is not None


def test_inspect_return_type():
    async def handler() -> dict:
        return {}

    meta = inspect_handler(handler)
    assert meta.return_type is dict


def test_inspect_no_return_annotation():
    async def handler():
        pass

    meta = inspect_handler(handler)
    assert meta.return_type is None


def test_inspect_ctx_and_info_together():
    async def handler(ctx: RequestContext, info: RequestInfo, value: str = ""):
        pass

    meta = inspect_handler(handler)
    assert meta.wants_ctx is True
    assert meta.wants_request_info is True
    assert meta.param_model is not None
    assert "value" in meta.param_model.model_fields


# ---------------------------------------------------------------------------
# Pydantic param model validation tests
# ---------------------------------------------------------------------------


def test_param_model_validates_correct_params():
    async def handler(name: str, count: int = 3):
        pass

    meta = inspect_handler(handler)
    assert meta.param_model is not None
    validated = meta.param_model.model_validate({"name": "test", "count": 5})
    assert validated.name == "test"  # type: ignore[attr-defined]
    assert validated.count == 5  # type: ignore[attr-defined]


def test_param_model_uses_defaults():
    async def handler(name: str, count: int = 3):
        pass

    meta = inspect_handler(handler)
    assert meta.param_model is not None
    validated = meta.param_model.model_validate({"name": "test"})
    assert validated.count == 3  # type: ignore[attr-defined]


def test_param_model_rejects_missing_required():
    import pytest

    async def handler(name: str, count: int = 3):
        pass

    meta = inspect_handler(handler)
    assert meta.param_model is not None
    with pytest.raises(Exception):
        meta.param_model.model_validate({"count": 5})


def test_param_model_rejects_wrong_type():
    import pytest

    async def handler(count: int):
        pass

    meta = inspect_handler(handler)
    assert meta.param_model is not None
    with pytest.raises(Exception):
        meta.param_model.model_validate({"count": "not_a_number"})


# ---------------------------------------------------------------------------
# validate_return tests
# ---------------------------------------------------------------------------


def test_validate_return_dict():
    validate_return({"a": 1}, dict)


def test_validate_return_wrong_type():
    import pytest

    with pytest.raises(TypeError):
        validate_return("string", dict)


def test_validate_return_none_type():
    # None return type should not raise
    validate_return("anything", type(None))


def test_validate_return_sse_queue():
    # SSEQueue (asyncio.Queue) should be skipped
    queue = asyncio.Queue()
    validate_return(queue, dict)


def test_validate_return_int():
    validate_return(42, int)


def test_validate_return_str():
    validate_return("hello", str)


def test_validate_return_list():
    validate_return([1, 2], list)


# ---------------------------------------------------------------------------
# JRPCService.registered_methods tests
# ---------------------------------------------------------------------------


def test_registered_methods_includes_builtins():
    from http_stream_transport.jsonrpc.jrpc_service import JRPCService

    svc = JRPCService()
    methods = svc.registered_methods()
    assert "initialize" in methods
    assert "notifications/initialized" in methods
    # Every value is a MethodRecord
    for name, rec in methods.items():
        assert isinstance(rec, MethodRecord)
        assert rec.name == name
    assert methods["initialize"].kind == "request"
    assert methods["notifications/initialized"].kind == "notification"


def test_registered_methods_includes_decorated():
    from http_stream_transport.jsonrpc.jrpc_service import JRPCService

    svc = JRPCService()

    @svc.request("test.echo")
    async def echo(**kwargs):
        return kwargs

    @svc.notification("test.ping")
    async def ping():
        pass

    methods = svc.registered_methods()
    assert "test.echo" in methods
    assert "test.ping" in methods
    # Keys are sorted
    assert list(methods.keys()) == sorted(methods.keys())

    # Verify MethodRecord fields for test.echo
    echo_rec = methods["test.echo"]
    assert echo_rec.name == "test.echo"
    assert echo_rec.kind == "request"
    assert echo_rec.is_async is True
    assert echo_rec.func is echo
    assert echo_rec.param_schema is None  # **kwargs only, no param model
    assert echo_rec.module == echo.__module__
    assert echo_rec.qualname == echo.__qualname__

    # Verify MethodRecord fields for test.ping
    ping_rec = methods["test.ping"]
    assert ping_rec.name == "test.ping"
    assert ping_rec.kind == "notification"
    assert ping_rec.is_async is True
    assert ping_rec.return_schema is None  # no return annotation


def test_method_record_with_typed_params():
    """MethodRecord captures param_schema and return_schema for typed handlers."""
    from http_stream_transport.jsonrpc.jrpc_service import JRPCService

    svc = JRPCService()

    @svc.request("math.add")
    async def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    rec = svc.registered_methods()["math.add"]
    assert rec.docstring == "Add two numbers."
    assert rec.param_schema is not None
    assert "properties" in rec.param_schema
    assert "a" in rec.param_schema["properties"]
    assert "b" in rec.param_schema["properties"]
    assert rec.return_schema is not None
    assert rec.return_schema.get("type") == "integer"


def test_build_method_record_directly():
    """build_method_record produces a correct MethodRecord from a function."""

    async def greet(name: str) -> str:
        """Say hello."""
        return f"hello {name}"

    meta = inspect_handler(greet)
    rec = build_method_record("test.greet", greet, meta, kind="request")

    assert rec.name == "test.greet"
    assert rec.func is greet
    assert rec.docstring == "Say hello."
    assert rec.is_async is True
    assert rec.param_schema is not None
    assert "name" in rec.param_schema["properties"]
    assert rec.return_schema == {"type": "string"}
