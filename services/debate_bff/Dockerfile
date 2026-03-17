FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared packages that debate-bff depends on
COPY packages/jrpc_common/ packages/jrpc_common/
COPY packages/client/ packages/client/

# Copy service dependency manifest
COPY services/debate_bff/pyproject.toml services/debate_bff/

# Install dependencies (without the project itself)
RUN uv sync --package debate-bff --no-install-project

# Copy source code
COPY services/debate_bff/src/ services/debate_bff/src/

# Install the project
RUN uv sync --package debate-bff

EXPOSE 80

ENV FE_PORT=80

CMD ["uv", "run", "--package", "debate-bff", "debate-bff"]