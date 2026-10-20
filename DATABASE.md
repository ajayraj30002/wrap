# Database

PostgreSQL is WRAP's primary persistence layer. Schema changes are managed with Alembic migrations.

## Migration

```bash
cd backend
venv\Scripts\alembic.exe upgrade head
```

## Tables

- `providers`: built-in provider metadata and enabled state.
- `credentials`: encrypted provider secrets, masked identifier, metadata, health status.
- `workers`: routable execution resources tied to provider, credential, model, and capabilities.
- `request_metrics`: one privacy-first telemetry record per completed, failed, or interrupted request.
- `quota_snapshots`: provider-reported, header-derived, estimated, or unknown quota observations.
- `health_events`: worker health status transitions.
- `routing_decisions`: candidates, selected worker, reason, and routing version.

`request_metrics` does not store prompts or responses. Quota source is explicit so gateway-observed usage, provider-reported quota, and estimates are never treated as the same thing.
