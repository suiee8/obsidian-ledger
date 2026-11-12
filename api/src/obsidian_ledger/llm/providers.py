"""The cloud model providers the Coach can use, each reached directly with an API key.

Every provider here speaks the OpenAI chat-completions format. Addresses are fixed: a user picks a
provider, never a URL, so journal data can only go to one of these services.

Endpoints checked 12 November 2026:
- Z.ai:       https://docs.z.ai/guides/develop/openai/python
- Moonshot:   https://api.moonshot.ai/v1 (OpenAI chat completions on /v1)
- OpenRouter: https://openrouter.ai/api/v1/models lists models with tool and JSON support
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    base_url: str  # chat completions are POST {base_url}/chat/completions
    key_page: str
    models: tuple[str, ...]  # offered when the provider's model list cannot be read
    free_models: tuple[str, ...] = ()
    json_mode: bool = True  # sends response_format {"type": "json_object"}
    extra_body: dict[str, Any] = field(default_factory=dict[str, Any])
    list_models: bool = True
    note: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": urlsplit(self.base_url).hostname,
            "key_page": self.key_page,
            "models": list(self.models),
            "free_models": list(self.free_models),
            "note": self.note,
        }


PROVIDERS: Final[dict[str, ProviderInfo]] = {
    "zai": ProviderInfo(
        id="zai",
        name="Z.ai (GLM)",
        base_url="https://api.z.ai/api/paas/v4",
        key_page="https://z.ai/manage-apikey/apikey-list",
        models=("glm-4.7-flash", "glm-4.5-flash", "glm-5.3-flash", "glm-5", "glm-5.3"),
        free_models=("glm-4.7-flash", "glm-4.5-flash"),
        # The Coach only rewords results, so step-by-step "thinking" just costs time and tokens.
        extra_body={"thinking": {"type": "disabled"}},
        list_models=False,
        note="GLM-4.7-Flash and GLM-4.5-Flash are free. GLM-5 models are paid per token.",
    ),
    "moonshot": ProviderInfo(
        id="moonshot",
        name="Moonshot (Kimi)",
        base_url="https://api.moonshot.ai/v1",
        key_page="https://platform.moonshot.ai/console/api-keys",
        models=("kimi-k2.6", "kimi-k3"),
        note="Paid per token. A Coach answer costs well under one US cent.",
    ),
    "openrouter": ProviderInfo(
        id="openrouter",
        name="OpenRouter (GLM, Kimi, and more)",
        base_url="https://openrouter.ai/api/v1",
        key_page="https://openrouter.ai/settings/keys",
        models=(
            "z-ai/glm-4.7-flash",
            "z-ai/glm-5.3-flash",
            "moonshotai/kimi-k2.6",
            "moonshotai/kimi-k3",
        ),
        note="One key for GLM and Kimi. Free models allow about 50 requests a day.",
    ),
}

NONE: Final = "none"
TEST_PROVIDER: Final = "test"


def test_provider(base_url: str) -> ProviderInfo:
    """A scripted model for the browser tests. Only registered when the test setting is present,
    and only on this computer."""
    host = urlsplit(base_url).hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("The test provider must run on this computer.")
    return ProviderInfo(
        id=TEST_PROVIDER,
        name="Test model (mock)",
        base_url=base_url.rstrip("/"),
        key_page="",
        models=("mock-coach",),
        free_models=("mock-coach",),
        note="Used by the automated tests only.",
    )


def catalog(test_url: str | None) -> dict[str, ProviderInfo]:
    found = dict(PROVIDERS)
    if test_url:
        found[TEST_PROVIDER] = test_provider(test_url)
    return found
