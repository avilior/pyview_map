set dotenv-load

bff_port := env("BFF_PORT", "8123")
places_port := env("PLACES_PORT", "8200")
flights_port := env("FLIGHTS_PORT", "8300")
github_user := env("GITHUB_USER", "avilior")
registry := "ghcr.io/" + github_user
git_sha := `git rev-parse --short HEAD`
platforms := "linux/amd64,linux/arm64"
builder := "publish_builder"

default:
    @just --list

# ---------------------------------------------------------------------------
# Local development (native processes)
# ---------------------------------------------------------------------------

# Install all workspace packages
install:
    uv sync --all-packages

# Run the BFF (pyview-map server)
bff:
    uv run --package pyview-map pyview-map

# Stop the BFF
stop-bff:
    pkill -f "pyview-map" 2>/dev/null || true

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

# Start Parks BE + BFF, open /places_demo
places: stop-all
    #!/usr/bin/env bash
    uv run --package places-backend places-backend &
    uv run --package pyview-map pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo

# Start Flights BE + BFF, open /flights
flights: stop-all
    #!/usr/bin/env bash
    uv run --package flights-backend flights-backend &
    uv run --package pyview-map pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{bff_port}}/flights

# Start both BEs + BFF, open both demos
all: stop-all
    #!/usr/bin/env bash
    uv run --package places-backend places-backend &
    uv run --package flights-backend flights-backend &
    uv run --package pyview-map pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo
    open http://localhost:{{bff_port}}/flights

# Stop everything (local)
stop-all: stop-parks-be stop-flights-be stop-bff

# ---------------------------------------------------------------------------
# Docker (containerized)
# ---------------------------------------------------------------------------

# Build all Docker images
docker-build:
    docker compose build

# Start all services in Docker, open both demos
docker-up:
    #!/usr/bin/env bash
    docker compose up -d
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo
    open http://localhost:{{bff_port}}/flights

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
    docker compose up -d places-backend bff
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo

# Start only flights in Docker
docker-flights:
    #!/usr/bin/env bash
    docker compose up -d flights-backend bff
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{bff_port}}/flights

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
        "bff|.|services/bff/Dockerfile" \
        "places-backend|.|services/places_backend/Dockerfile" \
        "flights-backend|.|services/flights_backend/Dockerfile"; do
        IFS='|' read -r name ctx dockerfile <<< "$svc"
        image="{{registry}}/pyview-map-${name}"
        echo ""
        echo "==> ${image}:{{git_sha}}"
        docker buildx build \
            --builder {{builder}} \
            --platform {{platforms}} \
            --tag "${image}:{{git_sha}}" \
            --tag "${image}:latest" \
            --ssh default \
            --push \
            -f "${dockerfile}" \
            "${ctx}"
    done
    echo ""
    echo "All images pushed:"
    echo "  {{registry}}/pyview-map-bff:{{git_sha}}"
    echo "  {{registry}}/pyview-map-places-backend:{{git_sha}}"
    echo "  {{registry}}/pyview-map-flights-backend:{{git_sha}}"

# Pull and start release images
release-up:
    #!/usr/bin/env bash
    docker compose -f docker-compose.release.yml pull
    docker compose -f docker-compose.release.yml up -d
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.5; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.5; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo
    open http://localhost:{{bff_port}}/flights

# Stop release services
release-down:
    docker compose -f docker-compose.release.yml down

# Tail release logs
release-logs:
    docker compose -f docker-compose.release.yml logs -f

# Show current release images in GHCR
release-list:
    #!/usr/bin/env bash
    for pkg in pyview-map-bff pyview-map-places-backend pyview-map-flights-backend; do
        echo "==> ${pkg}"
        docker image ls "{{registry}}/${pkg}" 2>/dev/null || echo "  (not pulled locally)"
        echo ""
    done
