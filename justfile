default:
    @just --list

# Install dependencies
install:
    uv sync

# Run the app
run:
    uv run pyview-map

# Open the map view in the browser
open-map:
    open http://localhost:8123/map

# Open the dynamic map view in the browser
open-dmap:
    open http://localhost:8123/dmap

# Stop any running pyview-map process
stop:
    pkill -f "pyview-map" 2>/dev/null || true

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

# Kill any running instance, start the app, and open /dmap in the browser
dmap: stop
    #!/usr/bin/env bash
    sleep 0.5
    uv run pyview-map &
    echo "Waiting for server..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    open http://localhost:8123/dmap
