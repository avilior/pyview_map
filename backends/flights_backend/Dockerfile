FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared package and dependency files (mirror repo layout for path deps)
COPY packages/dmap_models/ packages/dmap_models/
COPY backends/flights_backend/pyproject.toml backends/flights_backend/

WORKDIR /app/backends/flights_backend

# Install dependencies (without the project itself)
RUN --mount=type=ssh mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    uv sync --no-install-project

# Copy source code
COPY backends/flights_backend/src/ src/

# Install the project
RUN uv sync

EXPOSE 80

ENV FLIGHTS_PORT=80

CMD ["uv", "run", "flights-backend"]
