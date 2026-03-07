from dataclasses import dataclass

from pyview_map.views.components.shared.latlng import LatLng


@dataclass
class DPolyline:
    id: str
    name: str
    path: list[LatLng]
    color: str = "#3388ff"
    weight: int = 3
    opacity: float = 1.0
    dash_array: str | None = None

    @property
    def path_as_lists(self) -> list[list[float]]:
        return [ll.to_list() for ll in self.path]

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "name": self.name,
            "path": self.path_as_lists,
            "color": self.color,
            "weight": self.weight,
            "opacity": self.opacity,
        }
        if self.dash_array is not None:
            d["dashArray"] = self.dash_array
        return d
