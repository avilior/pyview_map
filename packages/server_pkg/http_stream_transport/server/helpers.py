from dataclasses import dataclass
from typing import Union, Sequence

from jrpc_common.jrpc_model import (
    JSONRPCRequest,
    JSONRPCNotification,
    JSONRPCResponse,
    JSONRPCErrorResponse,
    parse_jsonrpc,
    JSONRPCError,
    JSONRPC_INVALID_REQUEST,
)


@dataclass
class ClassifiedPayloads:
    requests: list[JSONRPCRequest]
    notifications: list[JSONRPCNotification]
    responses: list[JSONRPCResponse | JSONRPCErrorResponse]


def classify_payloads(
    raw_messages: Sequence[dict],
) -> Union[ClassifiedPayloads, JSONRPCErrorResponse]:
    requests: list[JSONRPCRequest] = []
    notifications: list[JSONRPCNotification] = []
    responses: list[JSONRPCResponse | JSONRPCErrorResponse] = []

    for raw in raw_messages:
        try:
            parsed = parse_jsonrpc(raw)
        except (ValueError, Exception) as e:
            # Invalid structure → JSON-RPC "Invalid Request" (-32600)
            return JSONRPCErrorResponse(
                id=raw.get("id") if isinstance(raw, dict) else None,
                error=JSONRPCError(code=JSONRPC_INVALID_REQUEST, message=f"Invalid JSON-RPC: {str(e)}"),
            )

        if isinstance(parsed, JSONRPCRequest):
            requests.append(parsed)
        elif isinstance(parsed, JSONRPCNotification):
            notifications.append(parsed)
        elif isinstance(parsed, (JSONRPCResponse, JSONRPCErrorResponse)):
            responses.append(parsed)

    return ClassifiedPayloads(requests=requests, notifications=notifications, responses=responses)
