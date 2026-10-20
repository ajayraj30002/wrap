# API

All `/v1` and `/api` routes require a WRAP API key:

```http
Authorization: Bearer wrap_xxx
```

## Public OpenAI-Compatible API

- `GET /v1/models`
- `POST /v1/chat/completions`

Supported chat parameters include `model`, `messages`, `temperature`, `max_tokens`, `max_completion_tokens`, `top_p`, `stream`, `stop`, `response_format`, `tools`, `tool_choice`, `presence_penalty`, `frequency_penalty`, `seed`, and `user`. Adapters forward only parameters that are safe for that provider.

## Health

- `GET /health`
- `GET /ready`

## Management API

- `GET /api/providers`
- `GET /api/providers/{id}`
- `POST /api/credentials`
- `GET /api/credentials`
- `PATCH /api/credentials/{id}`
- `DELETE /api/credentials/{id}`
- `POST /api/credentials/{id}/test`
- `GET /api/workers`
- `PATCH /api/workers/{id}`
- `GET /api/metrics/overview`
- `GET /api/metrics/workers`
- `GET /api/metrics/workers/{id}`
- `GET /api/metrics/requests`
- `POST /api/quota`
- `GET /api/quota`
- `GET /api/health/events`
- `GET /api/routing/decisions`

Credential responses include only masked provider keys.
