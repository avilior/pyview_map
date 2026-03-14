"""List commands — sent from external clients to control the browser list."""

from dataclasses import dataclass


@dataclass(slots=True)
class HighlightListItemCmd:
    """Scroll to and flash a list item."""

    id: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}highlightListItem", {"id": self.id}


ListCommand = HighlightListItemCmd
