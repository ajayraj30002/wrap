# Configuration

`.env` is bootstrap-only configuration. The dashboard never rewrites it, and provider credentials are stored in the database.

Required variables:

- `DATABASE_URL`: SQLAlchemy async URL, for example `postgresql+asyncpg://wrap:wrap@localhost:5432/wrap`.
- `WRAP_MASTER_KEY`: at least 32 characters, used to derive the encryption key for provider credentials.
- `WRAP_API_KEYS`: comma-separated WRAP gateway keys accepted by public and management APIs.

Optional variables:

- `HOST`: bind host, default `127.0.0.1`.
- `PORT`: bind port, default `8000`.
- `ENVIRONMENT`: `development`, `test`, or `production`.
- `LOG_LEVEL`: structured JSON log level.
- `CORS_ORIGINS`: JSON list of allowed dashboard origins.
- `REQUEST_TIMEOUT_SECONDS`: non-streaming provider timeout.
- `STREAM_IDLE_TIMEOUT_SECONDS`: streaming provider timeout.
- `MAX_REQUEST_BYTES`: reserved request-size control.

`WRAP_API_KEYS` authenticate callers to WRAP. Provider API keys are different secrets and are submitted through `POST /api/credentials`.
