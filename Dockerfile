FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./
COPY packages/dmap_models/ packages/dmap_models/

# Install dependencies (without the project itself)
RUN --mount=type=ssh mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    uv sync --no-install-project

# Copy source code
COPY src/ src/

# Install the project
RUN uv sync

EXPOSE 80

ENV BFF_PORT=80

CMD ["uv", "run", "pyview-map"]
