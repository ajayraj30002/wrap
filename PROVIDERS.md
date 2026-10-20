# Providers

Provider-specific behavior lives behind `ProviderAdapter`.

Current adapters:

- `groq`: OpenAI-compatible chat completions.
- `cerebras`: OpenAI-compatible chat completions.
- `gemini`: Gemini `generateContent` and `streamGenerateContent` normalized to OpenAI responses.

Adapters expose:

- capabilities
- default models
- request normalization
- non-streaming completion
- streaming completion
- credential test
- error normalization
- quota extraction where provider headers expose it

To add a provider:

1. Create an adapter under `src/providers`.
2. Register it in `src/providers/registry.py`.
3. Define default models and capabilities.
4. Add focused adapter tests.

The `/v1` route should not need provider-specific branches.
