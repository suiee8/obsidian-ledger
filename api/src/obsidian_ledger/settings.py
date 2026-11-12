from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. Secrets never belong in this model."""

    model_config = SettingsConfigDict(
        env_prefix="LEDGER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    data_dir: Path = Path(".ledger-data")
    max_upload_mb: int = 200
    default_timezone: str = "UTC"
    # Where provider API keys are kept: "keyring" (Windows Credential Manager) or "memory"
    # (tests only, so they never touch the real keychain).
    llm_secret_store: str = "keyring"
    # Tests only: an OpenAI-compatible mock on this computer, offered as an extra provider.
    llm_test_provider_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
