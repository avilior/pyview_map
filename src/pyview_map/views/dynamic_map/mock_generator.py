import math
import random
import uuid

from .dmarker import DMarker


_CALLSIGNS = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo",
    "Foxtrot", "Golf", "Hotel", "India", "Juliet",
    "Kilo", "Lima", "Mike", "November", "Oscar",
]

# Continental US bounding box
_LAT = (25.0, 49.0)
_LNG = (-125.0, -66.0)


def _random_latlng() -> list[float]:
    return [round(random.uniform(*_LAT), 4), round(random.uniform(*_LNG), 4)]


def _advance(marker: DMarker) -> list[float]:
    """Move marker along its heading with slight drift; bounce off US bounds."""
    angle = math.radians(marker.heading)
    dlat = marker.speed * math.cos(angle) * random.uniform(0.6, 1.4)
    dlng = marker.speed * math.sin(angle) * random.uniform(0.6, 1.4)

    # Gradual heading drift
    marker.heading = (marker.heading + random.uniform(-20, 20)) % 360

    lat = marker.lat_lng[0] + dlat
    lng = marker.lat_lng[1] + dlng

    # Bounce off bounds
    if not _LAT[0] <= lat <= _LAT[1]:
        marker.heading = (180 - marker.heading) % 360
        lat = max(_LAT[0], min(_LAT[1], lat))
    if not _LNG[0] <= lng <= _LNG[1]:
        marker.heading = (360 - marker.heading) % 360
        lng = max(_LNG[0], min(_LNG[1], lng))

    marker.lat_lng = [round(lat, 4), round(lng, 4)]
    return marker.lat_lng


class MockGenerator:
    MIN_MARKERS = 2
    MAX_MARKERS = 120

    def __init__(self, initial_count: int = 5) -> None:
        self._markers: dict[str, DMarker] = {}
        self._used_names: set[str] = set()
        self._counter = 0

        for _ in range(initial_count):
            self._create_marker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def markers(self) -> list[DMarker]:
        return list(self._markers.values())

    def next_update(self) -> dict:
        """Return one update event: op is 'add', 'delete', or 'update'."""
        n = len(self._markers)

        ops = ["move"] * 6
        if n < self.MAX_MARKERS:
            ops += ["add"] * 2
        if n > self.MIN_MARKERS:
            ops += ["delete"]

        op = random.choice(ops)

        if op == "move":
            marker = random.choice(list(self._markers.values()))
            new_latlng = _advance(marker)
            return {"op": "update", "id": marker.id, "name": marker.name, "latLng": new_latlng}

        if op == "add":
            marker = self._create_marker()
            return {"op": "add", "id": marker.id, "name": marker.name, "latLng": marker.lat_lng}

        # delete
        marker = random.choice(list(self._markers.values()))
        del self._markers[marker.id]
        return {"op": "delete", "id": marker.id}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _create_marker(self) -> DMarker:
        self._counter += 1
        # Pick an unused callsign; fall back to UUID suffix
        name = f"Unit-{self._counter:02d}"
        for callsign in _CALLSIGNS:
            candidate = f"{callsign}-{self._counter:02d}"
            if candidate not in self._used_names:
                name = candidate
                break

        self._used_names.add(name)
        mid = str(uuid.uuid4())[:8]
        marker = DMarker(id=mid, name=name, lat_lng=_random_latlng())
        self._markers[mid] = marker
        return marker
