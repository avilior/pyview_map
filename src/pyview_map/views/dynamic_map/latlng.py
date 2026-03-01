from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LatLng:
    lat: float
    lng: float

    def to_list(self) -> list[float]:
        return [self.lat, self.lng]

    @classmethod
    def from_list(cls, ll: list[float]) -> LatLng:
        return cls(lat=ll[0], lng=ll[1])
