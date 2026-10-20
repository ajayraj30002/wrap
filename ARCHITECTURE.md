# Architecture

WRAP separates the public OpenAI-compatible gateway from management APIs and provider-specific adapters.

```text
Client SDK
  -> /v1/chat/completions
  -> request validation
  -> Scheduler
  -> Worker
  -> ProviderAdapter
  -> Provider API
  -> normalized OpenAI response
  -> lifecycle metrics
  -> PostgreSQL
```

## Core Modules

- `src/api/routes/openai.py`: OpenAI-compatible public API and SSE streaming.
- `src/api/routes/management.py`: dashboard/management API surface.
- `src/providers/base.py`: adapter contract, capabilities, and normalized errors.
- `src/providers/openai_compatible.py`: Groq and Cerebras adapters.
- `src/providers/gemini.py`: Gemini request/response normalization.
- `src/providers/registry.py`: provider discovery without route-level if/else chains.
- `src/scheduler.py`: Phase 1 least-recently-used worker selection.
- `src/services/lifecycle.py`: reusable request timing, usage, and status tracking.
- `src/services/persistence.py`: resilient metrics/quota/health persistence.
- `src/db/models.py`: SQLAlchemy 2.x relational schema.

Phase 1 deliberately does not implement AI routing, task decomposition, fallback chains, or multi-agent execution. The scheduler and adapter interfaces are intentionally small so Phase 2 can replace selection logic without rewriting gateway routes.
