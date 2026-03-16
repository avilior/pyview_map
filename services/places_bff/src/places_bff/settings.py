"""Places BFF settings — overridable via PLACES_BFF_* environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlacesBffSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLACES_BFF_")

    host: str = "0.0.0.0"
    port: int = 8124
    log_level: str = "INFO"

    # Backend service URL (BFF → BE)
    places_backend_url: str = "http://localhost:8200/api"

    # URL that BEs use to call back to this BFF (BE → BFF)
    callback_url: str = "http://localhost:8124/api"

    # Shared auth token for BE ↔ BFF communication
    auth_token: str = "tok-acme-001"


settings = PlacesBffSettings()
