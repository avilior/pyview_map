from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MarkerOpEvent:
    """Marker CRUD operation from the API (add/update/delete)."""

    op: str  # "add" | "update" | "delete"
    id: str
    name: str | None = None
    latLng: list[float] | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "marker-op", "op": self.op, "id": self.id}
        if self.name is not None:
            d["name"] = self.name
        if self.latLng is not None:
            d["latLng"] = self.latLng
        return d


@dataclass(slots=True)
class MarkerEvent:
    """Browser marker interaction (click, drag, etc.)."""

    event: str
    id: str
    name: str
    latLng: list[float]

    def to_dict(self) -> dict:
        return {
            "type": "marker-event",
            "event": self.event,
            "id": self.id,
            "name": self.name,
            "latLng": self.latLng,
        }


@dataclass(slots=True)
class MapEvent:
    """Browser map interaction (click, zoom, pan, etc.)."""

    event: str
    center: list[float]
    zoom: int
    latLng: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "type": "map-event",
            "event": self.event,
            "center": self.center,
            "zoom": self.zoom,
            "latLng": self.latLng,
        }


BroadcastEvent = MarkerOpEvent | MarkerEvent | MapEvent


def parse_event(params: dict) -> BroadcastEvent:
    """Reconstruct a typed event from a notification params dict."""
    etype = params.get("type")
    match etype:
        case "marker-op":
            return MarkerOpEvent(
                op=params["op"], id=params["id"],
                name=params.get("name"), latLng=params.get("latLng"),
            )
        case "marker-event":
            return MarkerEvent(
                event=params["event"], id=params["id"],
                name=params["name"], latLng=params["latLng"],
            )
        case "map-event":
            return MapEvent(
                event=params["event"], center=params["center"],
                zoom=params["zoom"], latLng=params.get("latLng"),
            )
        case _:
            raise ValueError(f"Unknown event type: {etype}")
