from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from src.api.routes import management, openai, auth, apikeys, analytics
from src.core.config import settings
from src.core.logging import configure_logging
from src.db.models import Base
from src.db.session import AsyncSessionLocal
from src.db.session import engine
from src.services.bootstrap import ensure_bootstrap_gateway_keys, ensure_builtin_providers
from src.services.catalog_reconciler import CatalogReconciler
from src.intelligence.router import IntelligentRouter
from src.intelligence.resources.resource_state_store import ResourceStateStore
from src.api.routes.openai import set_intelligent_router


configure_logging(settings.LOG_LEVEL)

# Global Phase 2A intelligent router
_intelligent_router: IntelligentRouter | None = None
_catalog_reconciler = CatalogReconciler()

app = FastAPI(
    title="WRAP Gateway",
    description="OpenAI-compatible gateway for routing requests across developer-managed provider credentials.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)




app.include_router(openai.router, prefix="/v1", tags=["OpenAI-compatible"])
app.include_router(openai.router, tags=["OpenAI-compatible-root"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(apikeys.router, prefix="/api/apikeys", tags=["API Keys"])
app.include_router(apikeys.router, prefix="/api/api-keys", tags=["API Keys Alias"])
app.include_router(management.router, prefix="/api", tags=["Management"])
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])
app.include_router(analytics.router, tags=["Analytics"])


from fastapi import HTTPException as StarletteHTTPException, Request
from fastapi.responses import JSONResponse

@app.exception_handler(StarletteHTTPException)
async def openai_compatible_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/v1"):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"message": str(exc.detail), "type": "invalid_request_error"}},
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.on_event("startup")
async def startup() -> None:
    global _intelligent_router
    if settings.ENVIRONMENT != "production" and settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    # Ensure rate_limit_rpm, allowed_model_groups, and budget/financial columns exist
    try:
        async with engine.begin() as conn:
            if "postgresql" in settings.DATABASE_URL:
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS rate_limit_rpm INTEGER DEFAULT 120;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS allowed_model_groups JSONB;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS max_budget_usd FLOAT;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS spend_usd FLOAT DEFAULT 0.0;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS value_saved_usd FLOAT DEFAULT 0.0;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS budget_reset_period VARCHAR(20) DEFAULT 'monthly';"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS budget_exceeded_action VARCHAR(24) DEFAULT 'hard_cap';"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS budget_reset_at TIMESTAMP WITH TIME ZONE;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS spend_velocity_limit_usd FLOAT;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS spend_velocity_window_sec INTEGER DEFAULT 300;"))
                await conn.execute(text("ALTER TABLE gateway_api_keys ADD COLUMN IF NOT EXISTS encrypted_key TEXT;"))
                
                await conn.execute(text("ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS cost_usd FLOAT DEFAULT 0.0;"))
                await conn.execute(text("ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS value_saved_usd FLOAT DEFAULT 0.0;"))
                await conn.execute(text("ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS is_cache_hit BOOLEAN DEFAULT FALSE;"))
                await conn.execute(text("ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS is_paid_key BOOLEAN DEFAULT FALSE;"))
                await conn.execute(text("ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS gateway_key_id UUID;"))
            elif "sqlite" in settings.DATABASE_URL:
                for col_sql in [
                    "ALTER TABLE gateway_api_keys ADD COLUMN rate_limit_rpm INTEGER DEFAULT 120;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN allowed_model_groups TEXT;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN max_budget_usd FLOAT;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN spend_usd FLOAT DEFAULT 0.0;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN value_saved_usd FLOAT DEFAULT 0.0;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN budget_reset_period VARCHAR(20) DEFAULT 'monthly';",
                    "ALTER TABLE gateway_api_keys ADD COLUMN budget_exceeded_action VARCHAR(24) DEFAULT 'hard_cap';",
                    "ALTER TABLE gateway_api_keys ADD COLUMN budget_reset_at DATETIME;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN spend_velocity_limit_usd FLOAT;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN spend_velocity_window_sec INTEGER DEFAULT 300;",
                    "ALTER TABLE gateway_api_keys ADD COLUMN encrypted_key TEXT;",
                    "ALTER TABLE request_metrics ADD COLUMN cost_usd FLOAT DEFAULT 0.0;",
                    "ALTER TABLE request_metrics ADD COLUMN value_saved_usd FLOAT DEFAULT 0.0;",
                    "ALTER TABLE request_metrics ADD COLUMN is_cache_hit BOOLEAN DEFAULT 0;",
                    "ALTER TABLE request_metrics ADD COLUMN is_paid_key BOOLEAN DEFAULT 0;",
                    "ALTER TABLE request_metrics ADD COLUMN gateway_key_id TEXT;",
                ]:
                    try:
                        await conn.execute(text(col_sql))
                    except Exception:
                        pass
    except Exception:
        pass

    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        await ensure_bootstrap_gateway_keys(session)
    
    # Phase 2A: Initialize intelligent router and resource state
    resource_store = ResourceStateStore()
    _intelligent_router = IntelligentRouter(resource_store)
    set_intelligent_router(_intelligent_router)
    
    async with AsyncSessionLocal() as session:
        await resource_store.initialize(session)
    resource_store.start_reconciliation(AsyncSessionLocal)
    _catalog_reconciler.start(AsyncSessionLocal)


@app.on_event("shutdown")
async def shutdown() -> None:
    global _intelligent_router
    if _intelligent_router:
        await _intelligent_router._resource_store.shutdown()
    await _catalog_reconciler.shutdown()


_app_start_time = __import__("time").time()


@app.get("/healthz", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    uptime = int(__import__("time").time() - _app_start_time)
    return {
        "status": "healthy",
        "service": "wrap-gateway",
        "version": "0.1.0",
        "uptime_seconds": uptime,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready", tags=["Health"])
async def ready_check():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("select 1"))
            db_ok = True
        except Exception:
            db_ok = False

        from src.db.models import Worker
        w_res = await session.execute(select(Worker).where(Worker.enabled == True))
        active_workers = len(w_res.scalars().all())

    is_ready = db_ok and (active_workers > 0)
    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "degraded",
            "database": "connected" if db_ok else "unavailable",
            "active_workers": active_workers,
            "router_initialized": _intelligent_router is not None,
        },
    )


@app.get("/metrics", tags=["Observability"])
async def prometheus_metrics():
    """Prometheus exposition metrics endpoint for SRE/Kubernetes monitoring."""
    from src.db.models import Worker, RequestMetric
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload
    from src.services.cache import gateway_cache
    from fastapi.responses import PlainTextResponse

    lines = []
    # 1. Gateway Cache metrics
    c_stats = gateway_cache.stats()
    lines.append("# HELP wrap_cache_hits_total Total number of gateway prompt cache hits.")
    lines.append("# TYPE wrap_cache_hits_total counter")
    lines.append(f"wrap_cache_hits_total {c_stats['total_hits']}")
    lines.append("# HELP wrap_cache_misses_total Total number of gateway prompt cache misses.")
    lines.append("# TYPE wrap_cache_misses_total counter")
    lines.append(f"wrap_cache_misses_total {c_stats['total_misses']}")
    lines.append("# HELP wrap_cache_entries Total active entries in the response cache.")
    lines.append("# TYPE wrap_cache_entries gauge")
    lines.append(f"wrap_cache_entries {c_stats['entries_count']}")
    lines.append("# HELP wrap_cache_tokens_saved_total Cumulative provider tokens saved by cache.")
    lines.append("# TYPE wrap_cache_tokens_saved_total counter")
    lines.append(f"wrap_cache_tokens_saved_total {c_stats['total_tokens_saved']}")

    async with AsyncSessionLocal() as session:
        # 2. Worker health gauges
        w_res = await session.execute(select(Worker).options(selectinload(Worker.provider)))
        workers = w_res.scalars().all()
        lines.append("# HELP wrap_worker_status Worker operational health status (1=healthy, 0=unhealthy/offline).")
        lines.append("# TYPE wrap_worker_status gauge")
        for w in workers:
            is_h = 1 if (w.enabled and w.health_status == "healthy") else 0
            p_name = w.provider.name if w.provider else "unknown"
            lines.append(f'wrap_worker_status{{worker_id="{w.id}",model="{w.model}",provider="{p_name}",enabled="{str(w.enabled).lower()}"}} {is_h}')

        # 3. Overall request counter
        total_reqs = (await session.execute(select(func.count(RequestMetric.id)))).scalar() or 0
        lines.append("# HELP wrap_requests_total Total requests processed through WRAP.")
        lines.append("# TYPE wrap_requests_total counter")
        lines.append(f"wrap_requests_total {total_reqs}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=settings.ENVIRONMENT == "development")
