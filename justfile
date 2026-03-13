default:
    @just --list

# Install dependencies
install:
    uv sync

# Run the BFF (pyview-map server)
run:
    uv run pyview-map

# Stop any running pyview-map process
stop:
    pkill -f "pyview-map" 2>/dev/null || true

# Start the Parks Service BE on port 8200
be:
    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200

# Stop the Parks Service BE
stop-be:
    pkill -f "parks_service:app" 2>/dev/null || true

# Start BE + BFF, open /places_demo in the browser
places: stop stop-be
    #!/usr/bin/env bash
    sleep 0.5
    cd backends/places_backend && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200 &
    echo "Waiting for BE..."
    until curl -s -o /dev/null http://localhost:8200/api/health; do sleep 0.3; done
    echo "BE ready."

    uv run pyview-map &
    echo "Waiting for BFF..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "BFF ready."

    open http://localhost:8123/places_demo

# Start the Flights Service BE on port 8300
flights-be:
    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300

# Stop the Flights Service BE
stop-flights-be:
    pkill -f "flights_service:app" 2>/dev/null || true

# Start Flights BE + BFF, open /flights in the browser
flights: stop stop-flights-be
    #!/usr/bin/env bash
    sleep 0.5
    cd backends/flights_backend && uv run uvicorn flights_service:app --host 0.0.0.0 --port 8300 &
    echo "Waiting for Flights BE..."
    until curl -s -o /dev/null http://localhost:8300/api/health; do sleep 0.3; done
    echo "Flights BE ready."

    uv run pyview-map &
    echo "Waiting for BFF..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "BFF ready."

    open http://localhost:8123/flights

# Stop everything
stop-all: stop-be stop-flights-be stop
