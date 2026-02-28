import random
from dataclasses import dataclass, field


@dataclass
class DMarker:
    id: str
    name: str
    lat_lng: list[float]
    heading: float = field(default_factory=lambda: random.uniform(0, 360))
    speed: float = field(default_factory=lambda: random.uniform(0.4, 1.2))

    @property
    def lat(self) -> float:
        return self.lat_lng[0]

    @property
    def lng(self) -> float:
        return self.lat_lng[1]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "latLng": self.lat_lng}
