from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pyview_map.components.shared.latlng import LatLng

NOTIFICATION_METHOD = "notifications/map.event"


@dataclass(slots=True)
class MarkerOpEvent:
    """Marker CRUD operation from the API (add/update/delete)."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    op: str  # "add" | "update" | "delete"
    id: str
    name: str | None = None
    latLng: LatLng | None = None
    icon: str | None = None
    heading: float | None = None
    speed: float | None = None
    channel: str | None = None
    cid: str | None = None

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
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class MarkerEvent:
    """Browser marker interaction (click, drag, etc.)."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    event: str
    id: str
    name: str
    latLng: LatLng
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "type": "marker-event",
            "event": self.event,
            "id": self.id,
            "name": self.name,
            "latLng": self.latLng.to_list(),
        }
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class MapEvent:
    """Browser map interaction (click, zoom, pan, etc.)."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    event: str
    center: LatLng
    zoom: int
    latLng: LatLng | None = None
    bounds: tuple[LatLng, LatLng] | None = None  # (sw, ne)
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "type": "map-event",
            "event": self.event,
            "center": self.center.to_list(),
            "zoom": self.zoom,
            "latLng": self.latLng.to_list() if self.latLng else None,
        }
        if self.bounds is not None:
            d["bounds"] = [self.bounds[0].to_list(), self.bounds[1].to_list()]
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class PolylineOpEvent:
    """Polyline CRUD operation from the API (add/update/delete)."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    op: str  # "add" | "update" | "delete"
    id: str
    name: str | None = None
    path: list[LatLng] | None = None
    color: str | None = None
    weight: int | None = None
    opacity: float | None = None
    dashArray: str | None = None
    channel: str | None = None
    cid: str | None = None

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
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class PolylineEvent:
    """Browser polyline interaction (click, etc.)."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    event: str
    id: str
    name: str
    latLng: LatLng
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "type": "polyline-event",
            "event": self.event,
            "id": self.id,
            "name": self.name,
            "latLng": self.latLng.to_list(),
        }
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class MapReadyEvent:
    """Map component is mounted and ready in the browser."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    channel: str | None = None
    cid: str | None = None

    def retained_key(self) -> str:
        return f"map-ready:{self.channel}"

    def to_dict(self) -> dict:
        d: dict = {"type": "map-ready"}
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


MapBroadcastEvent = MarkerOpEvent | MarkerEvent | MapEvent | PolylineOpEvent | PolylineEvent | MapReadyEvent


def parse_map_event(params: dict) -> MapBroadcastEvent:
    """Parse a map/marker/polyline event from notification params."""
    etype = params.get("type")
    channel = params.get("channel")
    cid = params.get("cid")
    match etype:
        case "marker-op":
            raw_ll = params.get("latLng")
            return MarkerOpEvent(
                op=params["op"],
                id=params["id"],
                name=params.get("name"),
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
                icon=params.get("icon"),
                heading=params.get("heading"),
                speed=params.get("speed"),
                channel=channel,
                cid=cid,
            )
        case "marker-event":
            return MarkerEvent(
                event=params["event"],
                id=params["id"],
                name=params["name"],
                latLng=LatLng.from_list(params["latLng"]),
                channel=channel,
                cid=cid,
            )
        case "map-event":
            raw_ll = params.get("latLng")
            raw_bounds = params.get("bounds")
            return MapEvent(
                event=params["event"],
                center=LatLng.from_list(params["center"]),
                zoom=params["zoom"],
                latLng=LatLng.from_list(raw_ll) if raw_ll else None,
                bounds=(LatLng.from_list(raw_bounds[0]), LatLng.from_list(raw_bounds[1])) if raw_bounds else None,
                channel=channel,
                cid=cid,
            )
        case "polyline-op":
            raw_path = params.get("path")
            return PolylineOpEvent(
                op=params["op"],
                id=params["id"],
                name=params.get("name"),
                path=[LatLng.from_list(p) for p in raw_path] if raw_path else None,
                color=params.get("color"),
                weight=params.get("weight"),
                opacity=params.get("opacity"),
                dashArray=params.get("dashArray"),
                channel=channel,
                cid=cid,
            )
        case "polyline-event":
            return PolylineEvent(
                event=params["event"],
                id=params["id"],
                name=params["name"],
                latLng=LatLng.from_list(params["latLng"]),
                channel=channel,
                cid=cid,
            )
        case "map-ready":
            return MapReadyEvent(channel=channel, cid=cid)
        case _:
            raise ValueError(f"Unknown map event type: {etype}")


# ---------------------------------------------------------------------------
# Map commands — sent from external clients to control the browser map
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SetViewCmd:
    latLng: LatLng
    zoom: int

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}setView", {"latLng": self.latLng.to_list(), "zoom": self.zoom}


@dataclass(slots=True)
class PanToCmd:
    latLng: LatLng

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}panTo", {"latLng": self.latLng.to_list()}


@dataclass(slots=True)
class FlyToCmd:
    latLng: LatLng
    zoom: int

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}flyTo", {"latLng": self.latLng.to_list(), "zoom": self.zoom}


@dataclass(slots=True)
class FitBoundsCmd:
    corner1: LatLng
    corner2: LatLng

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}fitBounds", {"corner1": self.corner1.to_list(), "corner2": self.corner2.to_list()}


@dataclass(slots=True)
class FlyToBoundsCmd:
    corner1: LatLng
    corner2: LatLng

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}flyToBounds", {"corner1": self.corner1.to_list(), "corner2": self.corner2.to_list()}


@dataclass(slots=True)
class SetZoomCmd:
    zoom: int

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}setZoom", {"zoom": self.zoom}


@dataclass(slots=True)
class ResetViewCmd:
    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}resetView", {}


@dataclass(slots=True)
class HighlightMarkerCmd:
    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightMarker", {"id": self.id}


@dataclass(slots=True)
class HighlightPolylineCmd:
    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightPolyline", {"id": self.id}


@dataclass(slots=True)
class FollowMarkerCmd:
    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}followMarker", {"id": self.id}


@dataclass(slots=True)
class UnfollowMarkerCmd:
    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}unfollowMarker", {}


MapCommand = (
    SetViewCmd
    | PanToCmd
    | FlyToCmd
    | FitBoundsCmd
    | FlyToBoundsCmd
    | SetZoomCmd
    | ResetViewCmd
    | HighlightMarkerCmd
    | HighlightPolylineCmd
    | FollowMarkerCmd
    | UnfollowMarkerCmd
)
