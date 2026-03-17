"""FastAPI dependencies for Accept header validation on MCP endpoints."""

from fastapi import HTTPException, Request


def require_post_accept(request: Request) -> None:
    """Validate that the POST Accept header includes both required types.

    Spec §2: The client MUST include an Accept header listing both
    application/json and text/event-stream.
    """
    accept_header = request.headers.get("accept", "")
    if not ("application/json" in accept_header and "text/event-stream" in accept_header):
        raise HTTPException(
            status_code=406,
            detail="Not Acceptable: Accept header must include both application/json and text/event-stream",
        )


def require_get_accept(request: Request) -> None:
    """Validate that the GET Accept header includes text/event-stream."""
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" not in accept_header:
        raise HTTPException(
            status_code=406,
            detail="Not Acceptable: Accept header must include text/event-stream",
        )
