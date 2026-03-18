FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared packages that debate-backend depends on
COPY packages/jrpc_common/ packages/jrpc_common/
COPY packages/server_pkg/ packages/server_pkg/

# Copy service dependency manifest
COPY services/debate_backend/pyproject.toml services/debate_backend/

# Install dependencies (without the project itself)
RUN uv sync --package debate-backend --no-install-project

# Copy source code
COPY services/debate_backend/src/ services/debate_backend/src/

# Copy data to /data (clean, mountable path)
COPY services/debate_backend/data/ /data/

# Install the project
RUN uv sync --package debate-backend

EXPOSE 80

ENV BE_PORT=80
ENV DEBATE_DATA_DIR=/data

CMD ["uv", "run", "--package", "debate-backend", "debate-backend"]