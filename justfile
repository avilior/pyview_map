set dotenv-load

flights_bff_port := env("FLIGHTS_BFF_PORT", "8123")
places_bff_port := env("PLACES_BFF_PORT", "8124")
places_port := env("PLACES_PORT", "8200")
flights_port := env("FLIGHTS_PORT", "8300")
be_port := env("BE_PORT", "8000")
fe_port := env("FE_PORT", "8001")
github_user := env("GITHUB_USER", "avilior")
registry := "ghcr.io/" + github_user
git_sha := `git rev-parse --short HEAD`
platforms := "linux/amd64,linux/arm64"
builder := "publish_builder"

default:
    @just --list

# ---------------------------------------------------------------------------
# Local development — Flights & Places
# ---------------------------------------------------------------------------

# Install all workspace packages
install:
    uv sync --all-packages

# Run the Flights BFF
flights-bff:
    uv run --package flights-bff flights-bff

# Stop the Flights BFF
stop-flights-bff:
    pkill -f "flights-bff" 2>/dev/null || true

# Run the Places BFF
places-bff:
    uv run --package places-bff places-bff

# Stop the Places BFF
stop-places-bff:
    pkill -f "places-bff" 2>/dev/null || true

# Start the Parks Service BE
parks-be:
    uv run --package places-backend places-backend

# Stop the Parks Service BE
stop-parks-be:
    pkill -f "places-backend" 2>/dev/null || true

# Start the Flights Service BE
flights-be:
    uv run --package flights-backend flights-backend

# Stop the Flights Service BE
stop-flights-be:
    pkill -f "flights-backend" 2>/dev/null || true

# Start Parks BE + Places BFF, open /places_demo
places: stop-all
    #!/usr/bin/env bash
    uv run --package places-backend places-backend &
    uv run --package places-bff places-bff &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{places_bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{places_bff_port}}/places_demo

# Start Flights BE + Flights BFF, open /flights
flights: stop-all
    #!/usr/bin/env bash
    uv run --package flights-backend flights-backend &
    uv run --package flights-bff flights-bff &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{flights_bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{flights_bff_port}}/flights

# ---------------------------------------------------------------------------
# Local development — Debate
# ---------------------------------------------------------------------------

# Start the debate backend (port {{be_port}})
debate-backend:
    uv run --package debate-backend debate-backend

# Stop the debate backend
stop-debate-backend:
    pkill -f "debate-backend" 2>/dev/null || true

# Start the debate BFF (port {{fe_port}})
debate-bff:
    FE_PORT={{fe_port}} uv run --package debate-bff debate-bff

# Stop the debate BFF
stop-debate-bff:
    pkill -f "debate-bff" 2>/dev/null || true

# Start debate backend + BFF and open browser
debate: stop-all
    #!/usr/bin/env bash
    uv run --package debate-backend debate-backend &
    FE_PORT={{fe_port}} uv run --package debate-bff debate-bff &
    echo "Waiting for backend..."
    until curl -s -o /dev/null http://localhost:{{be_port}}/health; do sleep 0.3; done
    echo "Waiting for BFF..."
    until curl -s -o /dev/null http://localhost:{{fe_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{fe_port}}

# ---------------------------------------------------------------------------
# Local development — All services
# ---------------------------------------------------------------------------

# Start all BEs + all BFFs, open all demos
all: stop-all
    #!/usr/bin/env bash
    uv run --package places-backend places-backend &
    uv run --package flights-backend flights-backend &
    uv run --package flights-bff flights-bff &
    uv run --package places-bff places-bff &
    uv run --package debate-backend debate-backend &
    FE_PORT={{fe_port}} uv run --package debate-bff debate-bff &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{flights_bff_port}}; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{places_bff_port}}; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{be_port}}/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{fe_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{flights_bff_port}}/flights
    open http://localhost:{{places_bff_port}}/places_demo
    open http://localhost:{{fe_port}}

# Stop everything (local)
stop-all: stop-parks-be stop-flights-be stop-flights-bff stop-places-bff stop-debate-backend stop-debate-bff

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

# Run transport tests (packages/server_pkg)
test-transport:
    cd packages/server_pkg && uv run pytest -v

# Run debate application tests
test-debate:
    cd services/debate_backend && uv run pytest -v

# Run client tests
test-client:
    cd packages/client && uv run pytest -v

# Run all tests
test: test-transport test-debate test-client

# ---------------------------------------------------------------------------
# Docker (containerized)
# ---------------------------------------------------------------------------

# Build all Docker images
docker-build:
    docker compose build

# Start all services in Docker, open all demos
docker-up:
    #!/usr/bin/env bash
    docker compose up -d
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_bff_port}}; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{places_bff_port}}; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{be_port}}/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{fe_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{flights_bff_port}}/flights
    open http://localhost:{{places_bff_port}}/places_demo
    open http://localhost:{{fe_port}}

# Stop all Docker services
docker-down:
    docker compose down

# Tail Docker logs
docker-logs:
    docker compose logs -f

# Rebuild and restart all Docker services
docker-restart: docker-down docker-build docker-up

# Start only places in Docker
docker-places:
    #!/usr/bin/env bash
    docker compose up -d places-backend places-bff
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{places_bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{places_bff_port}}/places_demo

# Start only flights in Docker
docker-flights:
    #!/usr/bin/env bash
    docker compose up -d flights-backend flights-bff
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{flights_bff_port}}/flights

# Start only debate in Docker
docker-debate:
    #!/usr/bin/env bash
    docker compose up -d debate-backend debate-bff
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{be_port}}/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{fe_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{fe_port}}

# ---------------------------------------------------------------------------
# Release (build multi-arch images → push to GHCR → deploy from registry)
# ---------------------------------------------------------------------------

# Log in to GitHub Container Registry
release-login:
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u {{github_user}} --password-stdin

# Build and push all multi-arch images to GHCR
release-build: release-login
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Building and pushing images for {{platforms}} (commit {{git_sha}})..."
    for svc in \
        "flights-bff|.|services/flights_bff/Dockerfile" \
        "places-bff|.|services/places_bff/Dockerfile" \
        "places-backend|.|services/places_backend/Dockerfile" \
        "flights-backend|.|services/flights_backend/Dockerfile" \
        "debate-backend|.|services/debate_backend/Dockerfile" \
        "debate-bff|.|services/debate_bff/Dockerfile"; do
        IFS='|' read -r name ctx dockerfile <<< "$svc"
        image="{{registry}}/pyview-map-${name}"
        echo ""
        echo "==> ${image}:{{git_sha}}"
        docker buildx build \
            --builder {{builder}} \
            --platform {{platforms}} \
            --tag "${image}:{{git_sha}}" \
            --tag "${image}:latest" \
            --push \
            -f "${dockerfile}" \
            "${ctx}"
    done
    echo ""
    echo "All images pushed:"
    echo "  {{registry}}/pyview-map-flights-bff:{{git_sha}}"
    echo "  {{registry}}/pyview-map-places-bff:{{git_sha}}"
    echo "  {{registry}}/pyview-map-places-backend:{{git_sha}}"
    echo "  {{registry}}/pyview-map-flights-backend:{{git_sha}}"
    echo "  {{registry}}/pyview-map-debate-backend:{{git_sha}}"
    echo "  {{registry}}/pyview-map-debate-bff:{{git_sha}}"

# Pull and start release images
release-up:
    #!/usr/bin/env bash
    docker compose -f docker-compose.release.yml pull
    docker compose -f docker-compose.release.yml up -d
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_bff_port}}; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{places_bff_port}}; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{be_port}}/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{fe_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{flights_bff_port}}/flights
    open http://localhost:{{places_bff_port}}/places_demo
    open http://localhost:{{fe_port}}

# Stop release services
release-down:
    docker compose -f docker-compose.release.yml down

# Tail release logs
release-logs:
    docker compose -f docker-compose.release.yml logs -f

# Deploy files to a remote server via scp
# Usage: just deploy user@server [/path/on/server]
deploy host dest="~/docker/pyview-map":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Deploying to {{host}}:{{dest}}..."
    ssh {{host}} "mkdir -p {{dest}}"
    scp docker-compose.release.yml {{host}}:{{dest}}/
    scp justfile.deploy {{host}}:{{dest}}/justfile
    scp .env.example {{host}}:{{dest}}/.env.example
    echo ""
    echo "Done. On the remote server:"
    echo "  cd {{dest}}"
    echo "  cp .env.example .env   # edit with your settings"
    echo "  just up                # pull + start all services"

# Show current release images in GHCR
release-list:
    #!/usr/bin/env bash
    for pkg in pyview-map-flights-bff pyview-map-places-bff pyview-map-places-backend pyview-map-flights-backend pyview-map-debate-backend pyview-map-debate-bff; do
        echo "==> ${pkg}"
        docker image ls "{{registry}}/${pkg}" 2>/dev/null || echo "  (not pulled locally)"
        echo ""
    done
