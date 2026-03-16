FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared package
COPY packages/dmap_models/ packages/dmap_models/

# Copy service dependency manifest
COPY services/flights_backend/pyproject.toml services/flights_backend/

# Install dependencies (without the project itself)
RUN --mount=type=ssh mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    uv sync --package flights-backend --no-install-project

# Copy source code
COPY services/flights_backend/src/ services/flights_backend/src/

# Install the project
RUN uv sync --package flights-backend

EXPOSE 80

ENV FLIGHTS_PORT=80

CMD ["uv", "run", "--package", "flights-backend", "flights-backend"]
