FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared package
COPY packages/dmap_models/ packages/dmap_models/

# Copy service dependency manifest
COPY services/bff/pyproject.toml services/bff/

# Install dependencies (without the project itself)
RUN --mount=type=ssh mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    uv sync --package pyview-map --no-install-project

# Copy source code
COPY services/bff/src/ services/bff/src/

# Install the project
RUN uv sync --package pyview-map

EXPOSE 80

ENV BFF_PORT=80

CMD ["uv", "run", "--package", "pyview-map", "pyview-map"]
