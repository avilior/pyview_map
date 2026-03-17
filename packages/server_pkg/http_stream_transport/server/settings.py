from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Walk up from this file to find the monorepo root (contains ``Makefile``)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "Makefile").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enable_sse_get_endpoint: bool = False

    # Debate management paths (relative to monorepo root or absolute)
    debate_templates_dir: Path = Path("services/debate_backend/data/templates")
    debate_saves_dir: Path = Path("services/debate_backend/data/debates")
    debate_specs_dir: Path = Path("services/debate_backend/data/specs")

    @model_validator(mode="after")
    def _resolve_paths(self) -> "ServerSettings":
        """Resolve relative paths against the project root."""
        if not self.debate_templates_dir.is_absolute():
            self.debate_templates_dir = PROJECT_ROOT / self.debate_templates_dir
        if not self.debate_saves_dir.is_absolute():
            self.debate_saves_dir = PROJECT_ROOT / self.debate_saves_dir
        if not self.debate_specs_dir.is_absolute():
            self.debate_specs_dir = PROJECT_ROOT / self.debate_specs_dir
        return self


settings = ServerSettings()
