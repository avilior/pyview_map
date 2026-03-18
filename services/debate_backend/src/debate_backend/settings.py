"""Debate backend settings — overridable via DEBATE_* environment variables.

Local dev default: ``services/debate_backend/data/`` (relative to service root).
Container override: set ``DEBATE_DATA_DIR=/data`` in the Dockerfile.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default: <service_root>/data (works for local dev without any env vars)
_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DATA_DIR = _SERVICE_ROOT / "data"


class DebateSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEBATE_")

    data_dir: Path = _DEFAULT_DATA_DIR

    @property
    def templates_dir(self) -> Path:
        return self.data_dir / "templates"

    @property
    def saves_dir(self) -> Path:
        return self.data_dir / "debates"

    @property
    def specs_dir(self) -> Path:
        return self.data_dir / "specs"


settings = DebateSettings()
