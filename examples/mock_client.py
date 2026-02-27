"""mock_client.py — external JSON-RPC client that mirrors MockGenerator behaviour.

Run this while the server is up to see markers appear and move on the /dmap page:

    uv run python examples/mock_client.py
"""

import asyncio
import math
import random
import uuid

import httpx

RPC_URL = "http://localhost:8123/api/rpc"

# Continental US bounding box (same as MockGenerator)
_LAT = (25.0, 49.0)
_LNG = (-125.0, -66.0)

_CALLSIGNS = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo",
    "Foxtrot", "Golf", "Hotel", "India", "Juliet",
]


async def rpc(client: httpx.AsyncClient, method: str, params: dict, req_id: int = 1) -> dict:
    resp = await client.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "method": method, "params": params, "id": req_id},
    )
    resp.raise_for_status()
    return resp.json()


def _random_latlng() -> list[float]:
    return [round(random.uniform(*_LAT), 4), round(random.uniform(*_LNG), 4)]


def _advance(marker: dict) -> list[float]:
    """Move marker along its heading with slight drift; bounce off US bounds."""
    angle = math.radians(marker["heading"])
    speed = marker["speed"]
    dlat = speed * math.cos(angle) * random.uniform(0.6, 1.4)
    dlng = speed * math.sin(angle) * random.uniform(0.6, 1.4)

    marker["heading"] = (marker["heading"] + random.uniform(-20, 20)) % 360

    lat = marker["lat"] + dlat
    lng = marker["lng"] + dlng

    if not _LAT[0] <= lat <= _LAT[1]:
        marker["heading"] = (180 - marker["heading"]) % 360
        lat = max(_LAT[0], min(_LAT[1], lat))
    if not _LNG[0] <= lng <= _LNG[1]:
        marker["heading"] = (360 - marker["heading"]) % 360
        lng = max(_LNG[0], min(_LNG[1], lng))

    marker["lat"] = round(lat, 4)
    marker["lng"] = round(lng, 4)
    return [marker["lat"], marker["lng"]]


async def main() -> None:
    initial_count = 5

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Seed initial markers
        markers: dict[str, dict] = {}
        for i in range(initial_count):
            mid = str(uuid.uuid4())[:8]
            name = f"{_CALLSIGNS[i % len(_CALLSIGNS)]}-{i + 1:02d}"
            lat, lng = _random_latlng()
            markers[mid] = {
                "name": name,
                "lat": lat,
                "lng": lng,
                "heading": random.uniform(0, 360),
                "speed": random.uniform(0.4, 1.2),
            }
            await rpc(client, "markers.add", {"id": mid, "name": name, "latLng": [lat, lng]}, req_id=i)
            print(f"  added {name} at ({lat}, {lng})")

        print(f"\nSeeded {initial_count} markers. Starting update loop (Ctrl-C to stop)...\n")

        req_id = initial_count
        while True:
            await asyncio.sleep(1.2)
            mid, m = random.choice(list(markers.items()))
            new_latlng = _advance(m)
            req_id += 1
            await rpc(client, "markers.update", {"id": mid, "name": m["name"], "latLng": new_latlng}, req_id=req_id)
            print(f"  moved {m['name']} → ({new_latlng[0]}, {new_latlng[1]})")


if __name__ == "__main__":
    asyncio.run(main())
