"""Map commands — sent from external clients to control the browser map."""

from dataclasses import dataclass

from dmap_models.latlng import LatLng


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
