from dataclasses import dataclass
from typing import Any

from pyview_map.components.shared.latlng import LatLng


@dataclass
class DMarker:
    id: str
    name: str
    lat_lng: LatLng
    icon: str = "default"
    heading: float | None = None
    speed: float | None = None

    @property
    def lat(self) -> float:
        return self.lat_lng.lat

    @property
    def lng(self) -> float:
        return self.lat_lng.lng

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "name": self.name, "latLng": self.lat_lng.to_list(), "icon": self.icon}
        if self.heading is not None:
            d["heading"] = self.heading
        if self.speed is not None:
            d["speed"] = self.speed
        return d
