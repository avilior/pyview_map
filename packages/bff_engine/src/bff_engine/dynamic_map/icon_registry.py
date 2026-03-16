import json
from pathlib import Path


class IconRegistry:
    def __init__(self, path: Path | None = None):
        if path is None:
            path = Path(__file__).parent / "icons.json"
        self._icons: dict[str, dict] = json.loads(path.read_text())
        self._json: str = json.dumps(self._icons)

    def get(self, name: str) -> dict:
        return self._icons.get(name, self._icons["default"])

    def to_json(self) -> str:
        return self._json

    @property
    def names(self) -> list[str]:
        return list(self._icons.keys())


icon_registry = IconRegistry()
