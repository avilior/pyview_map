from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem
from pyview_map.views.components.shared.fan_out_source import FanOutSource


class APIListSource(FanOutSource):
    """List item fan-out source with channel/cid routing."""

    @property
    def items(self) -> list[DListItem]:
        return self._items_list()
