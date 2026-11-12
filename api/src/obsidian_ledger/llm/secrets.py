"""Where provider API keys are kept: Windows Credential Manager (or the platform keychain).

Keys never go into the database, an export, a log, or a response. The browser only ever learns
whether a key is saved and its last four characters.
"""

from __future__ import annotations

import threading
from typing import Final, Protocol

SERVICE: Final = "obsidian-ledger"


class Secrets(Protocol):
    def get(self, provider: str) -> str | None: ...
    def set(self, provider: str, key: str) -> None: ...
    def delete(self, provider: str) -> None: ...


class SecretError(Exception):
    """The keychain could not be read or written."""


class KeyringSecrets:
    def get(self, provider: str) -> str | None:
        import keyring
        from keyring.errors import KeyringError

        try:
            return keyring.get_password(SERVICE, provider)
        except KeyringError as exc:
            raise SecretError("The saved API key could not be read from the keychain.") from exc

    def set(self, provider: str, key: str) -> None:
        import keyring
        from keyring.errors import KeyringError

        try:
            keyring.set_password(SERVICE, provider, key)
        except KeyringError as exc:
            raise SecretError("The API key could not be saved to the keychain.") from exc

    def delete(self, provider: str) -> None:
        import keyring
        from keyring.errors import KeyringError, PasswordDeleteError

        try:
            keyring.delete_password(SERVICE, provider)
        except PasswordDeleteError:
            return  # nothing was saved
        except KeyringError as exc:
            raise SecretError("The API key could not be removed from the keychain.") from exc


class MemorySecrets:
    """For tests: keys live only as long as the process, and never touch the real keychain."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, provider: str) -> str | None:
        with self._lock:
            return self._keys.get(provider)

    def set(self, provider: str, key: str) -> None:
        with self._lock:
            self._keys[provider] = key

    def delete(self, provider: str) -> None:
        with self._lock:
            self._keys.pop(provider, None)


def make_secrets(kind: str) -> Secrets:
    return MemorySecrets() if kind == "memory" else KeyringSecrets()


def hint(key: str | None) -> str | None:
    """What may be shown about a saved key: its last four characters."""
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) >= 8 else "saved"
