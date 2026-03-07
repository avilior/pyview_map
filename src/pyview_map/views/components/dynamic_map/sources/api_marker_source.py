from pyview_map.views.components.dynamic_map.models.dmarker import DMarker
from pyview_map.views.components.shared.fan_out_source import FanOutSource
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# MarkerSource protocol — implement this to feed any data into DynamicMapLiveView
# ---------------------------------------------------------------------------


@runtime_checkable
class MarkerSource(Protocol):
    """
    A data source that provides markers and a stream of updates.

    Implement this protocol to connect any backend (GPS feed, database,
    simulation, etc.) to DynamicMapLiveView.
    """

    @property
    def markers(self) -> list[DMarker]:
        """Return the current set of markers (used for initial render)."""
        ...

    def next_update(self) -> dict:
        """
        Return the next marker operation as a dict:
            {"op": "add",    "id": str, "name": str, "latLng": [lat, lng]}
            {"op": "delete", "id": str}
            {"op": "update", "id": str, "name": str, "latLng": [lat, lng]}
        """
        ...


class APIMarkerSource(FanOutSource):
    """MarkerSource backed by fan-out queues with channel/cid routing."""

    @property
    def markers(self) -> list[DMarker]:
        return self._items_list()
