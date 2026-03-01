from __future__ import annotations

from dataclasses import dataclass

from .latlng import LatLng


@dataclass(slots=True)
class MarkerOpEvent:
    """Marker CRUD operation from the API (add/update/delete)."""

    op: str  # "add" | "update" | "delete"
    id: str
    name: str | None = None
    latLng: LatLng | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "marker-op", "op": self.op, "id": self.id}
        if self.name is not None:
            d["name"] = self.name
        if self.latLng is not None:
            d["latLng"] = self.latLng.to_list()
        return d


@dataclass(slots=True)
class MarkerEvent:
    """Browser marker interaction (click, drag, etc.)."""

    event: str
    id: str
    name: str
    latLng: LatLng

    def to_dict(self) -> dict:
        return {
            "type": "marker-event",
            "event": self.event,
            "id": self.id,
            "name": self.name,
            "latLng": self.latLng.to_list(),
        }


@dataclass(slots=True)
class MapEvent:
    """Browser map interaction (click, zoom, pan, etc.)."""

    event: str
    center: LatLng
    zoom: int
    latLng: LatLng | None = None

    def to_dict(self) -> dict:
        return {
            "type": "map-event",
            "event": self.event,
            "center": self.center.to_list(),
            "zoom": self.zoom,
            "latLng": self.latLng.to_list() if self.latLng else None,
        }


BroadcastEvent = MarkerOpEvent | MarkerEvent | MapEvent


def parse_event(params: dict) -> BroadcastEvent:
    """Reconstruct a typed event from a notification params dict."""
    etype = params.get("type")
    match etype:
        case "marker-op":
            raw_ll = params.get("latLng")
            return MarkerOpEvent(
                op=params["op"], id=params["id"],
                name=params.get("name"),
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
            )
        case "marker-event":
            return MarkerEvent(
                event=params["event"], id=params["id"],
                name=params["name"],
                latLng=LatLng.from_list(params["latLng"]),
            )
        case "map-event":
            raw_ll = params.get("latLng")
            return MapEvent(
                event=params["event"],
                center=LatLng.from_list(params["center"]),
                zoom=params["zoom"],
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
            )
        case _:
            raise ValueError(f"Unknown event type: {etype}")


# ---------------------------------------------------------------------------
# Map commands — sent from external clients to control the browser map
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SetViewCmd:
    latLng: LatLng
    zoom: int

    def to_push_event(self) -> tuple[str, dict]:
        return "setView", {"latLng": self.latLng.to_list(), "zoom": self.zoom}


@dataclass(slots=True)
class FlyToCmd:
    latLng: LatLng
    zoom: int

    def to_push_event(self) -> tuple[str, dict]:
        return "flyTo", {"latLng": self.latLng.to_list(), "zoom": self.zoom}


@dataclass(slots=True)
class FitBoundsCmd:
    corner1: LatLng
    corner2: LatLng

    def to_push_event(self) -> tuple[str, dict]:
        return "fitBounds", {"corner1": self.corner1.to_list(), "corner2": self.corner2.to_list()}


@dataclass(slots=True)
class FlyToBoundsCmd:
    corner1: LatLng
    corner2: LatLng

    def to_push_event(self) -> tuple[str, dict]:
        return "flyToBounds", {"corner1": self.corner1.to_list(), "corner2": self.corner2.to_list()}


@dataclass(slots=True)
class SetZoomCmd:
    zoom: int

    def to_push_event(self) -> tuple[str, dict]:
        return "setZoom", {"zoom": self.zoom}


@dataclass(slots=True)
class ResetViewCmd:
    def to_push_event(self) -> tuple[str, dict]:
        return "resetView", {}


@dataclass(slots=True)
class HighlightMarkerCmd:
    id: str

    def to_push_event(self) -> tuple[str, dict]:
        return "highlightMarker", {"id": self.id}


MapCommand = SetViewCmd | FlyToCmd | FitBoundsCmd | FlyToBoundsCmd | SetZoomCmd | ResetViewCmd | HighlightMarkerCmd
