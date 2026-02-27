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
