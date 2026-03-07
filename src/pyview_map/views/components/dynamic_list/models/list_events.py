from __future__ import annotations

from dataclasses import dataclass


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
class HighlightListItemCmd:
    """Scroll to and flash a list item."""

    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightListItem", {"id": self.id}


ListCommand = HighlightListItemCmd
