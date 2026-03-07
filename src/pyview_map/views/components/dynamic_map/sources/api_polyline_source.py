import asyncio

from pyview_map.views.components.dynamic_map.models.dpolyline import DPolyline
from pyview_map.views.components.shared.latlng import LatLng


class APIPolylineSource:
    """Polyline fan-out source with channel routing — structural clone of APIMarkerSource.

    Each LiveView connection creates its own instance with a dedicated
    bounded queue. Push methods fan out operations to matching subscriber queues.

    Subscribers are keyed by channel — a required routing group identifier.
    All instances subscribed to the same channel receive the same ops.

    The shared _polylines dict is partitioned by channel so initial state is isolated.
    """

    # channel → set of subscriber queues
    _subscribers: dict[str, set[asyncio.Queue]] = {}
    # channel → {polyline_id → DPolyline}
    _polylines: dict[str, dict[str, DPolyline]] = {}

    def __init__(self, *, channel: str):
        self._channel = channel
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        subs = type(self)._subscribers.setdefault(channel, set())
        subs.add(self._queue)

    @property
    def polylines(self) -> list[DPolyline]:
        return list(self.__class__._polylines.get(self._channel, {}).values())

    def next_update(self) -> dict:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return {"op": "noop"}

    @classmethod
    def _broadcast(cls, op: dict, *, channel: str) -> None:
        """Fan out an op to all subscribers of the given channel."""
        subs = cls._subscribers.get(channel)
        if not subs:
            return

        dead: list[asyncio.Queue] = []
        for q in subs:
            try:
                q.put_nowait(op)
            except asyncio.QueueFull:
                dead.append(q)

        for q in dead:
            subs.discard(q)

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
        cls._broadcast(op, channel=channel)

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
        cls._broadcast(op, channel=channel)

    @classmethod
    def push_delete(cls, id: str, *, channel: str) -> None:
        channel_polylines = cls._polylines.get(channel, {})
        channel_polylines.pop(id, None)
        cls._broadcast({"op": "delete", "id": id}, channel=channel)
