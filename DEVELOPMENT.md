# Development

## Backend Checks

```bash
cd backend
venv\Scripts\python.exe -m pytest -q
```

## Frontend Checks

```bash
cd frontend
npm run build
```

## Request Lifecycle

The gateway records:

```text
REQUEST_RECEIVED
REQUEST_VALIDATED
WORKER_SELECTED
REQUEST_STARTED
FIRST_TOKEN
REQUEST_COMPLETED | ERROR | STREAM_INTERRUPTED
METRICS_RECORDED
PERSISTED
```

Provider success, provider errors, timeouts, rate limits, authentication failures, connection failures, streaming interruption, and unexpected exceptions are represented in request metrics. Metrics persistence failures are logged and do not intentionally corrupt successful provider responses.
