from dataclasses import dataclass


@dataclass
class DListItem:
    id: str
    label: str
    subtitle: str = ""
