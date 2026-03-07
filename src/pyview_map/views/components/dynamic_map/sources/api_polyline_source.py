import asyncio

from pyview_map.views.components.dynamic_map.models.dpolyline import DPolyline
from pyview_map.views.components.shared.latlng import LatLng


class APIPolylineSource:
    """Polyline fan-out source with channel/cid routing — structural clone of APIMarkerSource.

    Subscribers are keyed by channel and cid. cid="*" broadcasts to all instances.
    The shared _polylines dict is partitioned by channel so initial state is isolated.
    """

    # channel → {cid → queue}
    _subscribers: dict[str, dict[str, asyncio.Queue]] = {}
    # channel → {polyline_id → DPolyline}
    _polylines: dict[str, dict[str, DPolyline]] = {}

    def __init__(self, *, channel: str, cid: str):
        self._channel = channel
        self._cid = cid
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, {})
        subs[cid] = self._queue

    @property
    def polylines(self) -> list[DPolyline]:
        return list(self.__class__._polylines.get(self._channel, {}).values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, channel: str, cid: str = "*") -> None:
        """Fan out an op to subscribers of the given channel.

        cid="*" broadcasts to all instances; a specific cid targets one instance.
        """
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        if cid == "*":
            dead: list[str] = []
            for instance_cid, q in subs.items():
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    dead.append(instance_cid)
            for instance_cid in dead:
                subs.pop(instance_cid, None)
        else:
            q = subs.get(cid)
            if q is not None:
                try:
                    q.put_nowait(op)
                except asyncio.QueueFull:
                    subs.pop(cid, None)

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
        channel_polylines = cls._polylines.setdefault(channel, {})
        channel_polylines[id] = DPolyline(
            id=id, name=name, path=path,
            color=color, weight=weight, opacity=opacity, dash_array=dash_array,
        )
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
        channel_polylines = cls._polylines.get(channel, {})
        if id in channel_polylines:
            p = channel_polylines[id]
            p.path = path
            p.name = name
            p.color = color
            p.weight = weight
            p.opacity = opacity
            p.dash_array = dash_array
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
        channel_polylines = cls._polylines.get(channel, {})
        channel_polylines.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, channel=channel, cid=cid)
