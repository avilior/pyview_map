"""Icon registry commands — broadcast to all MapDrivers."""

from dataclasses import dataclass


@dataclass(slots=True)
class UpdateIconRegistryCmd:
    registry_json: str

    def to_push_event(self, *, target: str = "") -> tuple[str, dict]:
        prefix = f"{target}:" if target else ""
        return f"{prefix}updateIconRegistry", {"registry": self.registry_json}
