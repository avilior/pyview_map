FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared packages
COPY packages/dmap_models/ packages/dmap_models/
COPY packages/server_pkg/ packages/server_pkg/
COPY packages/client/ packages/client/
COPY packages/jrpc_common/ packages/jrpc_common/

# Copy service dependency manifest
COPY services/places_backend/pyproject.toml services/places_backend/

# Install dependencies (without the project itself)
RUN uv sync --package places-backend --no-install-project

# Copy source code
COPY services/places_backend/src/ services/places_backend/src/

# Install the project
RUN uv sync --package places-backend

EXPOSE 80

ENV PLACES_PORT=80

CMD ["uv", "run", "--package", "places-backend", "places-backend"]
