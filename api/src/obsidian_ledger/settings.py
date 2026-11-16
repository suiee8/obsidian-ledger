from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. Secrets never belong in this model."""

    model_config = SettingsConfigDict(
        env_prefix="LEDGER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    data_dir: Path = Path(".ledger-data")
    max_upload_mb: int = 200
    requests_per_minute: int = Field(default=600, ge=1, le=10000)
    request_timeout_seconds: int = Field(default=120, ge=5, le=600)
    default_timezone: str = "UTC"
    # Where provider API keys are kept: "keyring" (Windows Credential Manager) or "memory"
    # (tests only, so they never touch the real keychain).
    llm_secret_store: str = "keyring"
    # Tests only: an OpenAI-compatible mock on this computer, offered as an extra provider.
    llm_test_provider_url: str | None = None

    # Hosts the API answers to. The default is loopback only.
    allowed_hosts: str = "127.0.0.1,localhost"
    # Opt-in public mode: login required, docs off, explicit origins required.
    public: bool = False
    # scrypt hash from `pnpm hash:password`. Never a plain password.
    password_hash: str | None = None
    session_idle_minutes: int = Field(default=30, ge=1, le=1440)
    # Opt-in read-only demo: every write is refused at the API layer.
    demo_readonly: bool = False
    # Optional malware scanner already installed on this computer: "off", "clamd", or "defender".
    scanner: Literal["off", "clamd", "defender"] = "off"
    # Untrusted files are read in a child process with these limits.
    parse_isolation: bool = True
    parse_timeout_seconds: int = Field(default=60, ge=1, le=600)
    parse_memory_mb: int = Field(default=4096, ge=256, le=32768)

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
