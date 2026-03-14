set dotenv-load

bff_port := env("BFF_PORT", "8123")
places_port := env("PLACES_PORT", "8200")
flights_port := env("FLIGHTS_PORT", "8300")

default:
    @just --list

# ---------------------------------------------------------------------------
# Local development (native processes)
# ---------------------------------------------------------------------------

# Install dependencies
install:
    uv sync

# Run the BFF (pyview-map server)
bff:
    uv run pyview-map

# Stop the BFF
stop-bff:
    pkill -f "pyview-map" 2>/dev/null || true

# Start the Parks Service BE
parks-be:
    cd backends/places_backend && uv run places-backend

# Stop the Parks Service BE
stop-parks-be:
    pkill -f "places-backend" 2>/dev/null || true

# Start the Flights Service BE
flights-be:
    cd backends/flights_backend && uv run flights-backend

# Stop the Flights Service BE
stop-flights-be:
    pkill -f "flights-backend" 2>/dev/null || true

# Start Parks BE + BFF, open /places_demo
places: stop-all
    #!/usr/bin/env bash
    cd backends/places_backend && uv run places-backend &
    uv run pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{places_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{bff_port}}/places_demo

# Start Flights BE + BFF, open /flights
flights: stop-all
    #!/usr/bin/env bash
    cd backends/flights_backend && uv run flights-backend &
    uv run pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:{{flights_port}}/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:{{bff_port}}; do sleep 0.3; done
    echo "Ready."
    open http://localhost:{{bff_port}}/flights

# Start both BEs + BFF, open both demos
all: stop-all
    #!/usr/bin/env bash
    cd backends/places_backend && uv run places-backend &
    cd backends/flights_backend && uv run flights-backend &
    uv run pyview-map &
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
