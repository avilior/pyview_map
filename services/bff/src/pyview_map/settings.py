"""BFF settings — overridable via BFF_* environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BffSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BFF_")

    host: str = "0.0.0.0"
    port: int = 8123
    log_level: str = "INFO"

    # Backend service URLs (BFF → BE)
    places_backend_url: str = "http://localhost:8200/api"
    flights_backend_url: str = "http://localhost:8300/api"

    # URL that BEs use to call back to this BFF (BE → BFF)
    callback_url: str = "http://localhost:8123/api"

    # Shared auth token for BE ↔ BFF communication
    auth_token: str = "tok-acme-001"


settings = BffSettings()
