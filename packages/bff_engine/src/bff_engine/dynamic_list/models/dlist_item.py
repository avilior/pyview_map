from dataclasses import dataclass, field
from typing import Any


@dataclass
class DListItem:
    id: str = field(metadata={"description": "Unique identifier for the list item. Assigned by the source"})
    label: str = field(metadata={"description": "Label for the list item."})
    subtitle: str = field(
        default="", metadata={"description": "Optional subtitle for the list item. Assigned by the source"}
    )
    data: dict[str, Any] = field(
        default_factory=dict, metadata={"description": "Arbitrary key-value data for custom rendering"}
    )
