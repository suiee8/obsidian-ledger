# ADR 0010: Store provider keys in the operating-system keychain

- Status: accepted
- Date: 2026-11-12

## Context

Provider credentials must not be persisted alongside journal data, returned to the browser, or copied into exports and logs.

## Decision

Use the OS keychain through `keyring` for saved provider keys. Persist only the provider selection and a masked key hint in application settings. The in-memory secrets implementation is for tests only.

## Consequences

- Keychain errors are reported without exposing the key.
- The browser can display only whether a key is saved and its final characters.
- Users manage keychain backups and removal through the application or their OS.
- Exported databases, files, reports, and ZIP archives do not contain provider keys.
