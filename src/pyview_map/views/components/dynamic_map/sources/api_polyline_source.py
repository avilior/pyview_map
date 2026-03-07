from pyview_map.views.components.dynamic_map.models.dpolyline import DPolyline
from pyview_map.views.components.shared.fan_out_source import FanOutSource


class APIPolylineSource(FanOutSource):
    """Polyline fan-out source with channel/cid routing."""

    @property
    def polylines(self) -> list[DPolyline]:
        return self._items_list()
