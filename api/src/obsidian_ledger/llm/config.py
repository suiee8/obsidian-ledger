"""Which cloud provider and model to use, the time limit, and which providers you agreed to send
data to. Saved as a preference, so it never changes analysis. API keys are kept elsewhere
(llm/secrets.py)."""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.store.db import Store

PREFERENCE: Final = "llm"
MODEL_NAME: Final = r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,99}$"
DEFAULT_SECONDS: Final = 30
MAX_SECONDS: Final = 600


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "none"
    model: str | None = Field(default=None, pattern=MODEL_NAME)
    # Seconds one summary or answer may take.
    answer_seconds: int = Field(default=DEFAULT_SECONDS, ge=10, le=MAX_SECONDS)
    # Providers you confirmed may receive aggregate results. A key alone is not consent.
    consented: list[str] = Field(default_factory=list[str])


def load_config(store: Store) -> LLMConfig:
    saved: Any = store.get_preferences().get(PREFERENCE)
    if isinstance(saved, dict):
        try:
            return LLMConfig.model_validate(saved)
        except ValueError:
            pass  # an old or hand-edited value: start again from the defaults
    return LLMConfig()


def save_config(store: Store, config: LLMConfig) -> None:
    store.set_preference(PREFERENCE, config.model_dump())
