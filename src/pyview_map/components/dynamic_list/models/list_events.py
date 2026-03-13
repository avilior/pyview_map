from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

NOTIFICATION_METHOD = "notifications/list.event"


@dataclass(slots=True)
class ListItemOpEvent:
    """API list item CRUD: add/delete/clear."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    op: str  # "add" | "delete" | "clear"
    id: str = ""
    label: str = ""
    subtitle: str = ""
    at: int = -1
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "list-item-op", "op": self.op}
        if self.id:
            d["id"] = self.id
        if self.label:
            d["label"] = self.label
        if self.subtitle:
            d["subtitle"] = self.subtitle
        if self.at != -1:
            d["at"] = self.at
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class ListItemClickEvent:
    """User clicked a list item in the browser."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    event: str
    id: str
    label: str
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "type": "list-item-event",
            "event": self.event,
            "id": self.id,
            "label": self.label,
        }
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


@dataclass(slots=True)
class ListReadyEvent:
    """List component is mounted and ready in the browser."""

    notification_method: ClassVar[str] = NOTIFICATION_METHOD
    channel: str | None = None
    cid: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": "list-ready"}
        if self.channel is not None:
            d["channel"] = self.channel
        if self.cid is not None:
            d["cid"] = self.cid
        return d


ListBroadcastEvent = ListItemOpEvent | ListItemClickEvent | ListReadyEvent


def parse_list_event(params: dict) -> ListBroadcastEvent:
    """Parse a list event from notification params."""
    etype = params.get("type")
    channel = params.get("channel")
    cid = params.get("cid")
    match etype:
        case "list-item-op":
            return ListItemOpEvent(
                op=params["op"],
                id=params.get("id", ""),
                label=params.get("label", ""),
                subtitle=params.get("subtitle", ""),
                at=params.get("at", -1),
                channel=channel, cid=cid,
            )
        case "list-item-event":
            return ListItemClickEvent(
                event=params["event"],
                id=params["id"],
                label=params["label"],
                channel=channel, cid=cid,
            )
        case "list-ready":
            return ListReadyEvent(channel=channel, cid=cid)
        case _:
            raise ValueError(f"Unknown list event type: {etype}")


@dataclass(slots=True)
class HighlightListItemCmd:
    """Scroll to and flash a list item."""

    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightListItem", {"id": self.id}


ListCommand = HighlightListItemCmd
