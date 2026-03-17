import asyncio
import json
from logging import getLogger

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from http_stream_transport.server.dependencies import require_get_accept, require_post_accept
from http_stream_transport.server.mock_tenant import get_tenant_by_token
from http_stream_transport.server.session import get_session
from http_stream_transport.server.settings import settings
from http_stream_transport.server.helpers import classify_payloads
from jrpc_common.jrpc_model import (
    JSONRPC_INVALID_REQUEST,
    JSONRPC_PARSE_ERROR,
    JSONRPCError,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCResponse,
)
from http_stream_transport.jsonrpc.jrpc_service import (
    RequestContext,
    SSEQueue,
    dispatch_notification,
    dispatch_request,
)

LOG = getLogger(__name__)


async def get_auth_token(
    authorization: str | None = Header(default=None),
) -> str:
    """Extract and validate the bearer token. Returns the token string.

    Raises HTTPException(401) if missing or invalid.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: valid Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ")
    tenant = get_tenant_by_token(token)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: tenant is not authorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_session_id(
    session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
) -> str | None:
    """Extract optional Mcp-Session-Id header from the request."""
    return session_id


router = APIRouter(
    prefix="/mcp",
    tags=["MCP"],
    dependencies=[
        Depends(get_auth_token),  # ensure that each endpoint has the Auth Record
        Depends(get_session_id),
    ],
)


def _attach_session_header(response: Response, session_id: str | None) -> Response:
    """Add Mcp-Session-Id header to the response if a session exists."""
    if session_id:
        response.headers["Mcp-Session-Id"] = session_id
    return response


@router.post(
    "",
    summary="Send JSON-RPC messages to the server",
    description="Accepts JSON-RPC requests, notifications, and responses per the MCP streaming spec.",
    responses={
        200: {"description": "SSE stream or JSON response for requests"},
        202: {"description": "Accepted — notification/response-only payload"},
        400: {"description": "JSON parse error or invalid JSON-RPC message"},
        401: {"description": "Unauthorized — valid Bearer token required"},
        403: {"description": "Forbidden — session belongs to a different tenant"},
        404: {"description": "Session not found or terminated"},
        406: {"description": "Not Acceptable — missing required Accept types"},
    },
)
async def mcp_post(
    request: Request,
    _accept: None = Depends(require_post_accept),
    auth_token: str = Depends(get_auth_token),
    session_id: str | None = Depends(get_session_id),
):
    """Handle a client POST to the MCP endpoint.

    Parses the JSON body, classifies each JSON-RPC message, enforces the
    batch mixing constraint, and returns either 202, JSON, or an SSE stream
    depending on message types and the client's Accept header.
    """

    # --- Step 0: Build request context --------------------------------------
    tenant = get_tenant_by_token(auth_token)
    assert tenant is not None, "tenant validated by get_auth_token dependency"
    existing_session = get_session(session_id) if session_id else None

    # Validate session if provided
    if session_id is not None:
        if existing_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or terminated",
            )
        if existing_session.tenant.tenant_id != tenant.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: session belongs to a different tenant",
            )

    # make a context to pass downstream....
    ctx = RequestContext(tenant=tenant, session=existing_session)

    # --- Step 1: Parse the raw JSON body -----------------------------------
    # A parse failure is a JSON-RPC "Parse error" (-32700).
    LOG.info(f"mcp_post called by tenant {tenant.tenant_id}")
    try:
        payload = await request.json()
    except Exception as e:
        error_resp = JSONRPCErrorResponse(
            id=None,
            error=JSONRPCError(code=JSONRPC_PARSE_ERROR, message=f"Invalid JSON: {str(e)}"),
        )
        return JSONResponse(content=error_resp.model_dump(), status_code=400)

    # --- Step 2: Normalise to a list ---------------------------------------
    # A single message is treated the same as a one-element batch internally.
    is_batch = isinstance(payload, list)
    raw_messages = payload if is_batch else [payload]

    # --- Step 3: Validate and classify each message ------------------------
    # parse_jsonrpc uses the presence of "method", "id", "result", and "error"
    # keys to distinguish the four JSON-RPC message types.  This avoids the
    # naive "id in msg" check which conflates requests with responses.
    incoming_rpc = classify_payloads(raw_messages)

    if isinstance(incoming_rpc, JSONRPCErrorResponse):
        return JSONResponse(content=incoming_rpc.model_dump(), status_code=400)

    # --- Step 4: Enforce batch mixing constraint (spec §3) -----------------
    # The spec defines two valid batch shapes:
    #   • requests and/or notifications (no responses)
    #   • responses only (no requests or notifications)
    # A batch that mixes both is rejected.
    if is_batch and incoming_rpc.responses and (incoming_rpc.requests or incoming_rpc.notifications):
        error_resp = JSONRPCErrorResponse(
            id=None,
            error=JSONRPCError(
                code=JSONRPC_INVALID_REQUEST,
                message="Invalid batch: responses must not be mixed with requests or notifications",
            ),
        )
        return JSONResponse(content=error_resp.model_dump(), status_code=400)

    # --- Step 5: Dispatch notifications ------------------------------------
    # Notifications are fire-and-forget; no JSON-RPC response is produced.
    for notification in incoming_rpc.notifications:
        await dispatch_notification(notification, ctx)

    # --- Step 6: Handle client responses -----------------------------------
    # These are replies to server-initiated requests sent on an earlier SSE
    # stream (e.g. the server asked the client for sampling or a root list).
    for response in incoming_rpc.responses:
        print(f"TODO Handle client response: {response}")

    # --- Step 7: If no requests, return 202 (spec §4) ---------------------
    # When the payload contains only notifications and/or responses the
    # server acknowledges with 202 Accepted and an empty body.
    if not incoming_rpc.requests:
        return _attach_session_header(Response(status_code=202), ctx.session_id)

    # --- Step 8: Handle initialize specially (no SSE needed) --------------
    # The initialize request creates a session and returns a simple JSON
    # response. It doesn't require an SSE channel.
    if len(incoming_rpc.requests) == 1 and incoming_rpc.requests[0].method == "initialize":
        resp = await dispatch_request(incoming_rpc.requests[0], ctx)
        assert isinstance(resp, (JSONRPCResponse, JSONRPCErrorResponse))
        return _attach_session_header(
            JSONResponse(content=resp.model_dump()),
            ctx.session_id,
        )

    # --- Step 9: Respond to other requests (spec §5-6) --------------------
    # When requests are present the server MUST return either:
    #   • Content-Type: text/event-stream  (SSE stream)
    #   • Content-Type: application/json   (single JSON body)
    # The server decides: if any handler returns an asyncio.Queue (streaming),
    # an SSE channel is required.  Otherwise, plain JSON is sufficient.

    # Dispatch all requests concurrently so batch items run in parallel.
    results: list[JSONRPCResponse | JSONRPCErrorResponse | SSEQueue] = list(
        await asyncio.gather(*(dispatch_request(msg, ctx) for msg in incoming_rpc.requests))
    )

    # note with this design we get here after the requests have a JRPCResonse (or Error) or they provided us with a SSE Queue
    # if any of the results needs an SSE queue we need to return an SSE response.
    needs_sse = any(isinstance(r, asyncio.Queue) for r in results)

    if needs_sse:

        async def generate_sse():
            event_id = 0

            # Emit non-queue results immediately
            for result in results:
                if not isinstance(result, asyncio.Queue):
                    event_id += 1
                    yield f"id: {event_id}\ndata: {json.dumps(result.model_dump())}\n\n"

            # Collect all queues and read from them concurrently so that
            # faster responses are emitted as soon as they arrive, regardless
            # of their position in the batch.
            queues = [r for r in results if isinstance(r, asyncio.Queue)]
            if not queues:
                return

            # Start a pending get() task for each queue
            pending: dict[asyncio.Task, asyncio.Queue] = {}
            for q in queues:
                task = asyncio.create_task(q.get())
                pending[task] = q

            while pending:
                done, _ = await asyncio.wait(pending.keys(), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    q = pending.pop(task)
                    item = task.result()
                    assert isinstance(
                        item,
                        (
                            JSONRPCNotification,
                            JSONRPCResponse,
                            JSONRPCErrorResponse,
                        ),
                    )
                    event_id += 1
                    yield f"id: {event_id}\ndata: {json.dumps(item.model_dump())}\n\n"
                    if isinstance(item, (JSONRPCResponse, JSONRPCErrorResponse)):
                        # Final response for this queue — track and stop reading
                        if ctx.session is not None and item.id is not None:
                            ctx.session.audit.track_response(item.id, item)
                    else:
                        # Notification — schedule the next read from this queue
                        new_task = asyncio.create_task(q.get())
                        pending[new_task] = q

        return _attach_session_header(
            StreamingResponse(
                generate_sse(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            ),
            ctx.session_id,
        )

    else:
        # JSON path: no handler requires streaming, return plain JSON.
        # If the original payload was a batch, return a JSON array;
        # otherwise return a single JSON object.
        # Since needs_sse is False, all results are JSONRPCResponse | JSONRPCErrorResponse.
        if is_batch:
            return _attach_session_header(
                JSONResponse(content=[r.model_dump() for r in results]),  # type: ignore[union-attr]
                ctx.session_id,
            )
        else:
            resp = results[0]
            assert isinstance(resp, (JSONRPCResponse, JSONRPCErrorResponse))
            return _attach_session_header(
                JSONResponse(content=resp.model_dump()),
                ctx.session_id,
            )


@router.get(
    "",
    summary="Open SSE stream for server-initiated messages",
    description="Opens a Server-Sent Events stream for receiving server-initiated JSON-RPC messages.",
    responses={
        200: {"description": "SSE stream of server-initiated messages"},
        401: {"description": "Unauthorized — valid Bearer token required"},
        405: {"description": "Method Not Allowed — SSE endpoint is disabled"},
        406: {"description": "Not Acceptable — Accept must include text/event-stream"},
    },
)
async def mcp_get(
    _accept: None = Depends(require_get_accept),
    auth_token: str = Depends(get_auth_token),
    session_id: str | None = Depends(get_session_id),
):
    """Handle GET requests to the MCP endpoint.

    Opens an SSE stream for server-initiated messages.

    Spec rules:
    - The client MUST include Accept: text/event-stream (406 if missing).
    - The server MAY disable the SSE endpoint via settings (405 if disabled).
    """

    # --- Validate session if provided ------------------------------------------
    tenant = get_tenant_by_token(auth_token)
    assert tenant is not None, "tenant validated by get_auth_token dependency"
    existing_session = get_session(session_id) if session_id else None

    if session_id is not None:
        if existing_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or terminated",
            )
        if existing_session.tenant.tenant_id != tenant.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: session belongs to a different tenant",
            )

    # --- Check if SSE endpoint is enabled --------------------------------------
    if not settings.enable_sse_get_endpoint:
        return Response(
            status_code=405,
            content="Method Not Allowed: SSE endpoint is disabled",
        )

    # TODO: return SSE stream for server-initiated messages (future work)
    async def generate_sse():
        yield "event: endpoint\ndata: \n\n"

    return _attach_session_header(
        StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        ),
        session_id,
    )
