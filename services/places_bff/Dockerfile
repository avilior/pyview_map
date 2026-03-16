FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy workspace root + lock
COPY pyproject.toml uv.lock ./

# Copy shared packages
COPY packages/dmap_models/ packages/dmap_models/
COPY packages/bff_engine/ packages/bff_engine/

# Copy service dependency manifest
COPY services/places_bff/pyproject.toml services/places_bff/

# Install dependencies (without the project itself)
RUN --mount=type=ssh mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    uv sync --package places-bff --no-install-project

# Copy source code
COPY services/places_bff/src/ services/places_bff/src/

# Install the project
RUN uv sync --package places-bff

EXPOSE 80

ENV PLACES_BFF_PORT=80

CMD ["uv", "run", "--package", "places-bff", "places-bff"]
