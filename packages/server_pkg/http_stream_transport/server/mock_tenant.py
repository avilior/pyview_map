"""Mock tenant registry for development and testing.

Provides a simple in-memory tenant store keyed by bearer token for O(1) lookup.
"""

from pydantic import BaseModel


class Tenant(BaseModel):
    tenant_id: str
    name: str
    token: str


# Pre-populated mock tenants keyed by their bearer token.
MOCK_TENANTS: dict[str, Tenant] = {
    "tok-acme-001": Tenant(tenant_id="t-acme", name="Acme Corp", token="tok-acme-001"),
    "tok-globex-002": Tenant(tenant_id="t-globex", name="Globex Inc", token="tok-globex-002"),
    "tok-initech-003": Tenant(tenant_id="t-initech", name="Initech LLC", token="tok-initech-003"),
}


def get_tenant_by_token(token: str) -> Tenant | None:
    """Look up a tenant by bearer token. Returns None if not found."""
    return MOCK_TENANTS.get(token)
