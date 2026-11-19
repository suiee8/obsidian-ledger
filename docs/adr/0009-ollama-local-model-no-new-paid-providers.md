# ADR 0009: Ollama is the only planned local model; no new paid provider integrations

- Status: accepted; local adapter deferred
- Date: 2026-11-12

## Context

Trading journals are private, and the rules-based Coach must work without an AI service. Local inference avoids sending journal data off-device, but supporting multiple local runtimes increases setup and testing cost.

## Decision

Ollama is the only local model runtime planned for this product, with `qwen2.5:7b` as the documented setup model. Do not add a new paid provider integration or any unsolicited model call in Phase 6.

The current cloud catalog includes Z.ai, Moonshot, and OpenRouter. These providers require a user-owned key and explicit consent. The Ollama adapter remains a planned integration. See the [provider catalog](../../api/src/obsidian_ledger/llm/providers.py).

## Consequences

- The deterministic Coach remains available with AI disabled and without network access.
- Any future local adapter must be tested against the existing tool and number-check boundaries.
- Adding Ollama support requires a separate implementation and validation task.
- Existing cloud providers can incur charges depending on the selected model and the user's provider account.
