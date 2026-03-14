"""List event wire-protocol types — shared contract between BFF and BEs."""

from __future__ import annotations

from dataclasses import dataclass

NOTIFICATION_METHOD = "notifications/list.event"


@dataclass(slots=True)
class ListItemOpEvent:
    """API list item CRUD: add/delete/clear."""

    op: str  # "add" | "delete" | "clear"
    id: str = ""
    label: str = ""
    subtitle: str = ""
    at: int = -1
    channel: str | None = None
    cid: str | None = None


@dataclass(slots=True)
class ListItemClickEvent:
    """User clicked a list item in the browser."""

    event: str
    id: str
    label: str
    channel: str | None = None
    cid: str | None = None


@dataclass(slots=True)
class ListReadyEvent:
    """List component is mounted and ready in the browser."""

    channel: str | None = None
    cid: str | None = None


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
                channel=channel,
                cid=cid,
            )
        case "list-item-event":
            return ListItemClickEvent(
                event=params["event"], id=params["id"], label=params["label"], channel=channel, cid=cid
            )
        case "list-ready":
            return ListReadyEvent(channel=channel, cid=cid)
        case _:
            raise ValueError(f"Unknown list event type: {etype}")
