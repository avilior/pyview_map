default:
    @just --list

# Install dependencies
install:
    uv sync

# Run the BFF (pyview-map server)
bff:
    uv run pyview-map

# Stop the BFF
stop-bff:
    pkill -f "pyview-map" 2>/dev/null || true

# Start the Parks Service BE on port 8200
parks-be:
    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200

# Stop the Parks Service BE
stop-parks-be:
    pkill -f "parks_service:app" 2>/dev/null || true

# Start the Flights Service BE on port 8300
flights-be:
    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300

# Stop the Flights Service BE
stop-flights-be:
    pkill -f "flights_service:app" 2>/dev/null || true

# Start Parks BE + BFF, open /places_demo
places: stop-all
    #!/usr/bin/env bash
    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200 &
    uv run pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:8200/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "Ready."
    open http://localhost:8123/places_demo

# Start Flights BE + BFF, open /flights
flights: stop-all
    #!/usr/bin/env bash
    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300 &
    uv run pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:8300/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "Ready."
    open http://localhost:8123/flights

# Start both BEs + BFF, open both demos
all: stop-all
    #!/usr/bin/env bash
    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200 &
    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300 &
    uv run pyview-map &
    echo "Waiting for services..."
    until curl -s -o /dev/null http://localhost:8200/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:8300/api/health; do sleep 0.3; done
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "Ready."
    open http://localhost:8123/places_demo
    open http://localhost:8123/flights

# Stop everything
stop-all: stop-parks-be stop-flights-be stop-bff
