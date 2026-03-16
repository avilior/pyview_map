"""Places backend settings — overridable via PLACES_* environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlacesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLACES_")

    host: str = "0.0.0.0"
    port: int = 8200
    log_level: str = "INFO"

    # Auth token used when connecting back to BFF
    bff_token: str = "tok-acme-001"


settings = PlacesSettings()
