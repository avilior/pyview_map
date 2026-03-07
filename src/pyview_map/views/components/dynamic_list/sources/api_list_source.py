from pyview_map.views.components.dynamic_list.models.dlist_item import DListItem
from pyview_map.views.components.shared.fan_out_source import FanOutSource


class APIListSource(FanOutSource):
    """List item fan-out source with channel/cid routing."""

    @property
    def items(self) -> list[DListItem]:
        return self._items_list()

    @classmethod
    def push_add(
        cls, id: str, label: str, subtitle: str = "",
        *, at: int = -1, channel: str, cid: str = "*",
    ) -> None:
        cls._store(channel, id, DListItem(id=id, label=label, subtitle=subtitle))
        cls._broadcast(
            {"op": "add", "id": id, "label": label, "subtitle": subtitle, "at": at},
            channel=channel, cid=cid,
        )

    @classmethod
    def push_remove(cls, id: str, *, channel: str, cid: str = "*") -> None:
        cls._remove(channel, id)
        cls._broadcast({"op": "delete", "id": id}, channel=channel, cid=cid)

    @classmethod
    def push_clear(cls, *, channel: str, cid: str = "*") -> None:
        cls._clear(channel)
        cls._broadcast({"op": "clear"}, channel=channel, cid=cid)
