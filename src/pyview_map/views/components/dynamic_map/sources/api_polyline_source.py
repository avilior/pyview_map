from pyview_map.views.components.dynamic_map.models.dpolyline import DPolyline
from pyview_map.views.components.shared.fan_out_source import FanOutSource
from pyview_map.views.components.shared.latlng import LatLng


class APIPolylineSource(FanOutSource):
    """Polyline fan-out source with channel/cid routing."""

    @property
    def polylines(self) -> list[DPolyline]:
        return self._items_list()

    @classmethod
    def push_add(
        cls,
        id: str,
        name: str,
        path: list[LatLng],
        color: str = "#3388ff",
        weight: int = 3,
        opacity: float = 1.0,
        dash_array: str | None = None,
        *,
        channel: str,
        cid: str = "*",
    ) -> None:
        cls._store(channel, id, DPolyline(
            id=id, name=name, path=path,
            color=color, weight=weight, opacity=opacity, dash_array=dash_array,
        ))
        op: dict = {
            "op": "add", "id": id, "name": name,
            "path": [ll.to_list() for ll in path],
            "color": color, "weight": weight, "opacity": opacity,
        }
        if dash_array is not None:
            op["dashArray"] = dash_array
        cls._broadcast(op, channel=channel, cid=cid)

    @classmethod
    def push_update(
        cls,
        id: str,
        name: str,
        path: list[LatLng],
        color: str = "#3388ff",
        weight: int = 3,
        opacity: float = 1.0,
        dash_array: str | None = None,
        *,
        channel: str,
        cid: str = "*",
    ) -> None:
        existing = cls._get(channel, id)
        if existing is not None:
            existing.path = path
            existing.name = name
            existing.color = color
            existing.weight = weight
            existing.opacity = opacity
            existing.dash_array = dash_array
        op: dict = {
            "op": "update", "id": id, "name": name,
            "path": [ll.to_list() for ll in path],
            "color": color, "weight": weight, "opacity": opacity,
        }
        if dash_array is not None:
            op["dashArray"] = dash_array
        cls._broadcast(op, channel=channel, cid=cid)

    @classmethod
    def push_delete(cls, id: str, *, channel: str, cid: str = "*") -> None:
        cls._remove(channel, id)
        cls._broadcast({"op": "delete", "id": id}, channel=channel, cid=cid)
