"""Flights BFF settings — overridable via FLIGHTS_BFF_* environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FlightsBffSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLIGHTS_BFF_")

    host: str = "0.0.0.0"
    port: int = 8123
    log_level: str = "INFO"

    # Backend service URL (BFF → BE)
    flights_backend_url: str = "http://localhost:8300/api"

    # URL that BEs use to call back to this BFF (BE → BFF)
    callback_url: str = "http://localhost:8123/api"

    # Shared auth token for BE ↔ BFF communication
    auth_token: str = "tok-acme-001"


settings = FlightsBffSettings()
