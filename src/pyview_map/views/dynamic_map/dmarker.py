import random
from dataclasses import dataclass, field

from .latlng import LatLng


@dataclass
class DMarker:
    id: str
    name: str
    lat_lng: LatLng
    heading: float = field(default_factory=lambda: random.uniform(0, 360))
    speed: float = field(default_factory=lambda: random.uniform(0.4, 1.2))

    @property
    def lat(self) -> float:
        return self.lat_lng.lat

    @property
    def lng(self) -> float:
        return self.lat_lng.lng

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "latLng": self.lat_lng.to_list()}
