# ==============================================================================
# Tier-1 Production Multi-Stage Dockerfile for WRAP AI Gateway Backend
# ==============================================================================

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Production runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

# Create unprivileged application user
RUN groupadd -g 10001 wrap && \
    useradd -u 10001 -g wrap -s /bin/sh -m wrapuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/wrapuser/.local
ENV PATH=/home/wrapuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy backend application source code
COPY --chown=wrapuser:wrap src/ /app/src/
COPY --chown=wrapuser:wrap alembic/ /app/alembic/
COPY --chown=wrapuser:wrap alembic.ini /app/alembic.ini

USER wrapuser

EXPOSE 8000

# Container liveness & readiness check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
