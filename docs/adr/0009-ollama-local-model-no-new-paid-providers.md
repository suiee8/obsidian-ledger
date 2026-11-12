# ADR 0009: Ollama is the only planned local model; no new paid provider integrations

- Status: accepted; local adapter deferred
- Date: 2026-11-12

## Context

Trading journals are private, and the rules-based Coach must work without an AI service. Local inference avoids sending journal data off-device, but supporting multiple local runtimes increases setup and testing cost.

## Decision

Ollama is the only local model runtime planned for this product, with `qwen2.5:7b` as the documented setup model. Do not add a new paid provider integration or any unsolicited model call in Phase 6.

The existing optional cloud-provider catalog remains unchanged for compatibility; those endpoints require a user-owned key and explicit consent. This decision does not claim that Ollama is already wired into this build: the current provider catalog has no Ollama adapter, so installing Ollama alone will not make it selectable.

## Consequences

- The deterministic Coach remains available with AI disabled and without network access.
- Any future local adapter must be tested against the existing tool and number-check boundaries.
- Adding Ollama support requires a separate implementation and validation task; this documentation-only phase does not change Coach logic.
- Existing cloud providers can incur charges depending on the selected model and the user's provider account.
