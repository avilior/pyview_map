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

# Kill any running instance, start the app, and open /dmap in the browser
dmap:
    #!/usr/bin/env bash
    pkill -f "pyview-map" 2>/dev/null || true
    sleep 0.5
    uv run pyview-map &
    echo "Waiting for server..."
    until curl -s -o /dev/null http://localhost:8123; do sleep 0.3; done
    open http://localhost:8123/dmap
