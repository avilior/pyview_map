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
    icon: str | None = None
    heading: float | None = None
    speed: float | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "marker-op", "op": self.op, "id": self.id}
        if self.name is not None:
            d["name"] = self.name
        if self.latLng is not None:
            d["latLng"] = self.latLng.to_list()
        if self.icon is not None:
            d["icon"] = self.icon
        if self.heading is not None:
            d["heading"] = self.heading
        if self.speed is not None:
            d["speed"] = self.speed
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


@dataclass(slots=True)
class PolylineOpEvent:
    """Polyline CRUD operation from the API (add/update/delete)."""

    op: str  # "add" | "update" | "delete"
    id: str
    name: str | None = None
    path: list[LatLng] | None = None
    color: str | None = None
    weight: int | None = None
    opacity: float | None = None
    dashArray: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "polyline-op", "op": self.op, "id": self.id}
        if self.name is not None:
            d["name"] = self.name
        if self.path is not None:
            d["path"] = [ll.to_list() for ll in self.path]
        if self.color is not None:
            d["color"] = self.color
        if self.weight is not None:
            d["weight"] = self.weight
        if self.opacity is not None:
            d["opacity"] = self.opacity
        if self.dashArray is not None:
            d["dashArray"] = self.dashArray
        return d


@dataclass(slots=True)
class PolylineEvent:
    """Browser polyline interaction (click, etc.)."""

    event: str
    id: str
    name: str
    latLng: LatLng

    def to_dict(self) -> dict:
        return {
            "type": "polyline-event",
            "event": self.event,
            "id": self.id,
            "name": self.name,
            "latLng": self.latLng.to_list(),
        }


BroadcastEvent = MarkerOpEvent | MarkerEvent | MapEvent | PolylineOpEvent | PolylineEvent


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
                icon=params.get("icon"),
                heading=params.get("heading"),
                speed=params.get("speed"),
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
        case "polyline-op":
            raw_path = params.get("path")
            return PolylineOpEvent(
                op=params["op"], id=params["id"],
                name=params.get("name"),
                path=[LatLng.from_list(p) for p in raw_path] if raw_path else None,
                color=params.get("color"),
                weight=params.get("weight"),
                opacity=params.get("opacity"),
                dashArray=params.get("dashArray"),
            )
        case "polyline-event":
            return PolylineEvent(
                event=params["event"], id=params["id"],
                name=params["name"],
                latLng=LatLng.from_list(params["latLng"]),
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


@dataclass(slots=True)
class HighlightPolylineCmd:
    id: str

    def to_push_event(self) -> tuple[str, dict]:
        return "highlightPolyline", {"id": self.id}


MapCommand = SetViewCmd | FlyToCmd | FitBoundsCmd | FlyToBoundsCmd | SetZoomCmd | ResetViewCmd | HighlightMarkerCmd | HighlightPolylineCmd
