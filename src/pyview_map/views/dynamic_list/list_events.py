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
        return d


@dataclass(slots=True)
class ListItemClickEvent:
    """User clicked a list item in the browser."""

    event: str
    id: str
    label: str

    def to_dict(self) -> dict:
        return {
            "type": "list-item-event",
            "event": self.event,
            "id": self.id,
            "label": self.label,
        }


@dataclass(slots=True)
class HighlightListItemCmd:
    """Scroll to and flash a list item."""

    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightListItem", {"id": self.id}


ListCommand = HighlightListItemCmd
