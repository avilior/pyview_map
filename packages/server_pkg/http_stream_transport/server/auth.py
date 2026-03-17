"""Authentication and session resolution for MCP endpoints.

Extracts the bearer token from the Authorization header, validates the tenant,
and manages the Mcp-Session-Id lifecycle.
"""

from dataclasses import dataclass

from fastapi.security import HTTPBearer

from http_stream_transport.server.mock_tenant import Tenant
from http_stream_transport.server.session import Session

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """Holds the resolved tenant and session for a request."""

    tenant: Tenant | None = None
    session: Session | None = None

    @property
    def session_id(self) -> str | None:
        return self.session.session_id if self.session else None


# def resolve_auth(
#     request: Request,
#     credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
# ) -> AuthContext:
#     """Resolve authentication and session from request headers.
#
#     Raises HTTPException on auth/session failures.
#     """
#
#     # --- Extract tenant from bearer token ------------------------------------
#     tenant: Tenant | None = None
#     if credentials is not None:
#         tenant = get_tenant_by_token(credentials.credentials)
#
#     # --- Enforce require_auth ------------------------------------------------
#     if settings.require_auth and tenant is None:
#         raise HTTPException(
#             status_code=401,
#             detail="Unauthorized: valid Bearer token required",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#
#     # --- Session resolution --------------------------------------------------
#     session_id_header = request.headers.get("Mcp-Session-Id")
#
#     if session_id_header:
#         # Client sent a session ID — validate it
#         session = get_session(session_id_header)
#         if session is None:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Session not found or terminated",
#             )
#         # Verify the session belongs to the requesting tenant
#         if tenant and session.tenant.tenant_id != tenant.tenant_id:
#             raise HTTPException(
#                 status_code=403,
#                 detail="Forbidden: session belongs to a different tenant",
#             )
#         return AuthContext(tenant=tenant, session=session)
#
#     # No session ID header — create a new session if authenticated
#     if tenant is not None:
#         session = create_session(tenant)
#         return AuthContext(tenant=tenant, session=session)
#
#     # No auth, no session — anonymous access (only allowed when require_auth=False)
#     return AuthContext()
