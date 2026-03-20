import json
from pathlib import Path

_BUILTIN_PATH = Path(__file__).parent / "icons.json"


class IconRegistry:
    def __init__(self, path: Path | None = None):
        # Always load built-in defaults first
        self._icons: dict[str, dict] = json.loads(_BUILTIN_PATH.read_text())
        self._builtin_names: frozenset[str] = frozenset(self._icons.keys())
        # Merge user-supplied file on top (if given)
        if path is not None:
            self._icons.update(json.loads(path.read_text()))
        self._json: str = json.dumps(self._icons)

    def get(self, name: str) -> dict:
        return self._icons.get(name, self._icons["default"])

    def to_json(self) -> str:
        return self._json

    @property
    def names(self) -> list[str]:
        return list(self._icons.keys())

    def register(self, name: str, definition: dict) -> None:
        """Add a new icon definition at runtime.

        Raises ValueError if the name already exists (built-in or dynamic).
        Use remove() first to replace a dynamic icon.
        """
        if name in self._icons:
            if name in self._builtin_names:
                raise ValueError(f"cannot overwrite built-in icon {name!r}")
            raise ValueError(f"icon {name!r} already exists; remove it first to replace")
        self._icons[name] = definition
        self._json = json.dumps(self._icons)

    def remove(self, name: str) -> bool:
        """Remove a dynamic icon by name. Returns True if removed, False if not found.

        Built-in icons cannot be removed.
        """
        if name in self._builtin_names or name not in self._icons:
            return False
        del self._icons[name]
        self._json = json.dumps(self._icons)
        return True

    @property
    def icons(self) -> dict[str, dict]:
        return dict(self._icons)


icon_registry = IconRegistry()


def configure(path: str | Path) -> None:
    """Re-initialize the global icon_registry from a file, merging on top of built-in defaults."""
    global icon_registry
    icon_registry = IconRegistry(Path(path))
