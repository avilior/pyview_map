FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared packages
COPY packages/dmap_models/ packages/dmap_models/
COPY packages/bff_engine/ packages/bff_engine/
COPY packages/server_pkg/ packages/server_pkg/
COPY packages/client/ packages/client/
COPY packages/jrpc_common/ packages/jrpc_common/

# Copy service dependency manifest
COPY services/flights_bff/pyproject.toml services/flights_bff/

# Install dependencies (without the project itself)
RUN uv sync --package flights-bff --no-install-project

# Copy source code
COPY services/flights_bff/src/ services/flights_bff/src/

# Install the project
RUN uv sync --package flights-bff

EXPOSE 80

ENV FLIGHTS_BFF_PORT=80

CMD ["uv", "run", "--package", "flights-bff", "flights-bff"]
