FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies (without the project itself)
RUN --mount=type=ssh uv sync --no-install-project --frozen 2>/dev/null || uv sync --no-install-project

# Copy source code
COPY src/ src/

# Install the project
RUN uv sync --frozen 2>/dev/null || uv sync

EXPOSE 80

ENV FLIGHTS_PORT=80

CMD ["uv", "run", "flights-backend"]
