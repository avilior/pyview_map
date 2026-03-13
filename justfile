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
    cd examples/list && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200

# Stop the Parks Service BE
stop-be:
    pkill -f "parks_service:app" 2>/dev/null || true

# Start BE + BFF, open /places_demo in the browser
places: stop stop-be
    #!/usr/bin/env bash
    sleep 0.5
    cd examples/list && uv run uvicorn parks_service:app --host 0.0.0.0 --port 8200 &
    echo "Waiting for BE..."
    until curl -s -o /dev/null http://localhost:8200/api/health; do sleep 0.3; done
    echo "BE ready."

    uv run pyview-map &
    echo "Waiting for BFF..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    echo "BFF ready."

    open http://localhost:8123/places_demo

# Open the dynamic map view in the browser
open-dmap:
    open http://localhost:8123/dmap

# Kill any running instance, start the app, and open /dmap in the browser
dmap: stop
    #!/usr/bin/env bash
    sleep 0.5
    uv run pyview-map &
    echo "Waiting for server..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    open http://localhost:8123/dmap

# Run the mock client (pushes markers via JSON-RPC); starts the server first if not already running
mock-run: mock-stop
    #!/usr/bin/env bash
    if ! curl -s -o /dev/null http://localhost:8123; then
        echo "Server not running — starting it..."
        uv run pyview-map &
        until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
        echo "Server ready."
    fi

    open http://localhost:8123/dmap

    echo "Starting client...."
    uv run python examples/mock_client.py
    echo "Ending client...."

# Stop the mock client
mock-stop:
    pkill -f "mock_client.py" 2>/dev/null || true

# Stop everything
stop-all: mock-stop stop-be stop
