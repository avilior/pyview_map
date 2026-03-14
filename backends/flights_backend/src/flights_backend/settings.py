"""Flights backend settings — overridable via FLIGHTS_* environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FlightsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLIGHTS_")

    host: str = "0.0.0.0"
    port: int = 8300
    log_level: str = "INFO"

    # Auth token used when connecting back to BFF
    bff_token: str = "tok-acme-001"


settings = FlightsSettings()
