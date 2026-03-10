from dataclasses import dataclass, field


@dataclass
class DListItem:
    id: str = field(metadata={"description": "Unique identifier for the list item. Assigned by the source"})
    label: str = field(metadata={"description": "Label for the list item."})
    subtitle: str = field(default="", metadata={"description": "Optional subtitle for the list item. Assigned by the source"})
    # todo: add more fields like an optional icon etc...
