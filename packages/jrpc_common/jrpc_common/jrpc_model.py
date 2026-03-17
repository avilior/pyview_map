from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 standard error codes
# https://www.jsonrpc.org/specification#error_object
# ---------------------------------------------------------------------------
JSONRPC_PARSE_ERROR = -32700  # Invalid JSON received by the server
JSONRPC_INVALID_REQUEST = -32600  # The JSON is not a valid JSON-RPC request
JSONRPC_METHOD_NOT_FOUND = -32601  # The method does not exist or is not available
JSONRPC_INVALID_PARAMS = -32602  # Invalid method parameter(s)
JSONRPC_INTERNAL_ERROR = -32603  # Internal JSON-RPC error
# Server error range: -32000 to -32099 (reserved for implementation-defined errors)

# Type aliases
JsonRpcId = int | str
JsonRpcParams = dict[str, Any] | list[Any]


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: JsonRpcParams | None = None
    id: JsonRpcId | None = None

    model_config = ConfigDict(extra="forbid")


class JSONRPCNotification(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: JsonRpcParams | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any | None = None

    model_config = ConfigDict(extra="forbid")


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: JsonRpcId | None
    result: Any

    model_config = ConfigDict(extra="forbid")


class JSONRPCErrorResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: JsonRpcId | None
    error: JSONRPCError

    model_config = ConfigDict(extra="forbid")


JSONRPCMessage = JSONRPCRequest | JSONRPCNotification | JSONRPCResponse | JSONRPCErrorResponse


def parse_jsonrpc(data: dict) -> JSONRPCMessage:
    """Inspect keys to determine the JSON-RPC message type and return a validated model."""
    if "method" in data:
        if "id" in data:
            return JSONRPCRequest.model_validate(data)
        return JSONRPCNotification.model_validate(data)
    if "result" in data:
        return JSONRPCResponse.model_validate(data)
    if "error" in data:
        return JSONRPCErrorResponse.model_validate(data)
    raise ValueError(f"Cannot determine JSON-RPC message type from keys: {set(data.keys())}")
