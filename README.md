# WRAP

WRAP means "Wrapping Free Tiers into an Ultimate Challenger".

It is an OpenAI-compatible AI gateway for routing developer requests across multiple provider credentials behind one endpoint.

Phase 1 focuses on the infrastructure foundation:

- OpenAI-compatible `POST /v1/chat/completions` and `GET /v1/models`
- Provider adapter registry for Groq, Cerebras, and Gemini
- Multiple encrypted credentials per provider
- Deterministic least-recently-used worker selection
- PostgreSQL persistence for providers, credentials, workers, request metrics, quota snapshots, health events, and routing decisions
- Management APIs for a developer dashboard
- Privacy-first telemetry that does not store prompts or responses by default

## Local Setup

```bash
cp backend/.env.example backend/.env
docker compose up -d postgres
cd backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\alembic.exe upgrade head
venv\Scripts\uvicorn.exe src.main:app --reload
```

The React dashboard runs separately:

```bash
cd frontend
npm install
npm run dev
```

## OpenAI-Compatible Usage

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer wrap_replace_with_a_long_random_gateway_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}]}'
```

Streaming uses OpenAI-style SSE:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer wrap_replace_with_a_long_random_gateway_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

## Multi-Agent DAG Orchestration & Cross-Provider Striping

Unlike traditional round-robin gateways, WRAP analyzes complex software and reasoning workloads and automatically decomposes them into a directed acyclic graph (DAG):

```
01 INGEST ──► 02 RESOLVER (DAG Partition) ──► [PARALLEL WORKSTREAMS] ──► 04 SYNTHESIZE ──► 05 VERDICT (200 OK)
                                              ├─ System Architecture & Data (Gemini Pro)
                                              ├─ API & Service Logic (Groq LPU)
                                              ├─ Client & Interface Layer (Groq / Cerebras)
                                              ├─ Testing & Verification (Validation Worker)
                                              └─ Cross-Contract Integration (Schema Aggregator)
```

- **Branch 1: System Architecture & Data** (`DEEP REASONING`) — Frontier Reasoner (Gemini Pro): Formulates database schemas, multi-tenant boundaries, and domain models.
- **Branch 2: API & Service Logic** (`BURST ENGINE`) — Groq LPU Ultra-Throughput: Procedural endpoints, authentication middleware, and RBAC security services at 500+ tok/s.
- **Branch 3: Client & Interface Layer** (`SPEED TIER`) — Fast Inference (Groq / Cerebras): Responsive React dashboards, interactive telemetry charts, and client state hooks.
- **Branch 4: Testing & Verification** (`FORMAL AUDIT`) — Validation Suite Worker: Pytest unit and integration test fixtures, edge-case harnesses, and regression validation suites.
- **Branch 5: Cross-Contract Integration** (`SYNTHESIS NODE`) — Schema & Interface Aggregator: Reconciles frontend-backend types, ensures OpenAPI schema adherence, and resolves dependency contracts before emission.

See [API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE.md](DATABASE.md), [PROVIDERS.md](PROVIDERS.md), [CONFIGURATION.md](CONFIGURATION.md), and [DEVELOPMENT.md](DEVELOPMENT.md).
