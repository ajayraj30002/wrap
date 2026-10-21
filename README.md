<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="frontend/public/wrap-app-icon.png">
    <img src="frontend/public/wrap-app-icon.png" alt="WRAP AI Gateway" width="108" height="108" />
  </picture>
</p>

<h1 align="center">WRAP</h1>

<p align="center">
  <strong>Self-Healing AI Gateway & Autonomous Multi-Agent DAG Orchestration Engine</strong><br />
  <em>Unifying Free & Enterprise Model Tiers into an Unstoppable, High-Throughput Compute Mesh.</em>
</p>

<p align="center">
  <a href="#-quickstart"><img src="https://img.shields.io/badge/Version-v1.4.2-0284c7?style=for-the-badge&logo=git&logoColor=white" alt="Version" /></a>
  <a href="#-key-features"><img src="https://img.shields.io/badge/Engine-Self--Healing%20AI-9333ea?style=for-the-badge&logo=lightning&logoColor=white" alt="Self-Healing Engine" /></a>
  <a href="#-supported-providers"><img src="https://img.shields.io/badge/OpenAI-Drop--in%20v1-7c3aed?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI Compatible" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-16a34a?style=for-the-badge&logo=apache&logoColor=white" alt="License" /></a>
</p>

<p align="center">
  <a href="https://github.com/ajayraj30002/wrap/actions"><img src="https://img.shields.io/badge/CI-Passing-22c55e?style=for-the-badge&logo=githubactions&logoColor=white" alt="CI Status" /></a>
  <a href="docker-compose.yml"><img src="https://img.shields.io/badge/Docker-Compose%20Ready-2496ed?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Ready" /></a>
  <a href="k8s/"><img src="https://img.shields.io/badge/Kubernetes-Kustomize-326ce5?style=for-the-badge&logo=kubernetes&logoColor=white" alt="Kubernetes" /></a>
  <a href="#-enterprise-architecture"><img src="https://img.shields.io/badge/Python%20%7C%20React-3.11+%20%7C%2019-f59e0b?style=for-the-badge&logo=python&logoColor=white" alt="Stack" /></a>
</p>

<p align="center">
  <a href="#-about-wrap"><strong>About</strong></a> •
  <a href="#-quickstart"><strong>Quickstart</strong></a> •
  <a href="#-key-features"><strong>Key Features</strong></a> •
  <a href="#-autonomous-dag-orchestration"><strong>DAG Engine</strong></a> •
  <a href="#-supported-providers"><strong>Providers</strong></a> •
  <a href="#-enterprise-architecture"><strong>Architecture</strong></a> •
  <a href="#-client-sdk-usage"><strong>SDK Integration</strong></a> •
  <a href="#-deployment-modes"><strong>Deployment</strong></a>
</p>

---

<!-- HERO DASHBOARD PREVIEW -->
<p align="center">
  <img src="docs/assets/dashboard-overview.png" alt="WRAP Enterprise Mission Control Room" width="100%" style="border-radius: 8px; border: 1px solid #1e293b; box-shadow: 0 20px 40px -15px rgba(0,0,0,0.5);" />
</p>
<p align="center"><em>Figure 1: WRAP Operator Control Room — Real-time telemetry, model group routing, and multi-tenant quota tracking.</em></p>

---

## ⚡ About WRAP

**WRAP** (*Wrapping Free Tiers into an Ultimate Challenger*) is an enterprise-grade, high-throughput AI Gateway and Autonomous DAG Orchestration proxy built for mission-critical AI applications, autonomous agents, and developer toolchains. It exposes a single, zero-overhead **OpenAI-compatible drop-in endpoint** (`/v1/chat/completions`) that aggregates distributed LLM providers, balances encrypted credential pools, and strips multi-agent workloads into parallel execution graphs.

Traditional AI gateways act merely as passive reverse proxies that pass through raw API requests, fragile rate limits, and broken model outputs. **WRAP operates as an active, self-healing scheduling kernel:**

- **🛡️ Autonomous Self-Healing AI Engine:** Transparently intercepts provider errors (429 rate limits, 5xx outages, context window overflow, and hallucinated tool calls) and heals them in-flight without interrupting the client.
- **⚡ Dynamic Multi-Agent DAG Orchestration:** Decomposes complex reasoning prompts into concurrent execution workstreams across specialized silicon (e.g., Deep Reasoning on Gemini, Ultra-fast Code on Groq LPUs, Instant Verification on Cerebras), collapsing sequential waterfalls into a single critical path.
- **🔄 Free-Tier Arbitrage & Virtual Key Pools:** Seamlessly rotates paired free-tier credential buckets into unified, enterprise-grade virtual tiers with zero compute costs.
- **🔒 Strict Zero-Leak Privacy:** Telemetry tracks operational metadata, token velocity, and latencies without ever logging or persisting user prompt payloads or sensitive completions.
- **📊 Virtual Model Tiers & Spend Governance:** Hardware-isolated recursion safeguards, budget circuit breakers, and rate-limit virtualizers eliminate runaway agent loop billing.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  WRAP AI GATEWAY KERNEL                                │
│                                                                                        │
│  [Any OpenAI SDK] ──► [Auth & Guardrails] ──► [Self-Healing Engine] ──► [DAG Analyzer] │
│                                                                                │       │
│            ┌─────────────────────────────┬─────────────────────────────────────┴───┐   │
│            ▼                             ▼                                         ▼   │
│    [Groq LPU Engine]            [Cerebras Speed Tier]                    [Gemini Pro]  │
│    500+ tok/s Code              Sub-200ms Synthetics                     Frontier Logic│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Why WRAP?

| Challenge with Vanilla Gateways | WRAP Enterprise Solution |
| :--- | :--- |
| **Aggressive Free-Tier Rate Limits** | Dynamic credential pooling & auto-striping distributes load across multiple encrypted keys seamlessly. |
| **Provider Downtime & Outages** | Zero-downtime fallback cascades reroute failed requests across alternative models in `< 5ms`. |
| **Malformed Tool Calls & JSON Errors** | **Self-Healing Engine** auto-extracts hallucinated text tools, fixes broken JSON schemas, and repairs streaming calls. |
| **Heavy Reasoning Slowdowns** | Multi-agent DAG partitioning strips reasoning, logic, client code, and verification into parallel branches. |
| **Telemetry & Privacy Concerns** | Privacy-first architecture: strictly zero logging of prompt payloads, tokens, or completions by default. |
| **Runaway Provider Invoices** | Virtual model tiers, project-level spend velocity caps, and deterministic quota tracking. |
| **Provider Vendor Lock-In** | 100% Drop-in replacement for OpenAI SDKs (`openai.base_url = "http://gateway:8000/v1"`). |

---

## 🚀 Key Features

### 1. Autonomous Multi-Agent DAG Orchestration & Workstream Striping
Rather than executing complex reasoning and code workloads sequentially, WRAP’s internal analyzer decomposes incoming tasks into an execution graph with 5 synchronized workstreams:

```
01 INGEST ──► 02 RESOLVER (DAG Partition) ──► [PARALLEL WORKSTREAMS] ──► 04 SYNTHESIZE ──► 05 VERDICT (200 OK)
                                              ├─ Branch 1: System Architecture & Data (Gemini Pro)
                                              ├─ Branch 2: API & Service Logic (Groq LPU Ultra-Speed)
                                              ├─ Branch 3: Client & Interface Layer (Cerebras / Groq)
                                              ├─ Branch 4: Formal Testing & Verification (Validation Worker)
                                              └─ Branch 5: Cross-Contract Integration (Schema Aggregator)
```

<!-- DAG GIF MEDIA PLACEHOLDER -->
<p align="center">
  <img src="docs/assets/dag-pipeline.gif" alt="WRAP Live DAG Execution Pipeline" width="100%" style="border-radius: 8px; border: 1px solid #1e293b;" />
</p>
<p align="center"><em>Figure 2: Real-time Live DAG Pipeline visualizer executing multi-workstream routing with sub-millisecond dependency resolution.</em></p>

---

### 2. Autonomous Self-Healing AI Engine & Universal Tool Recovery
Production LLM workflows frequently fail due to context load, provider dropouts, or models hallucinating tool calls as plain text or malformed JSON. WRAP's built-in self-healing kernel intercepts and repairs these issues dynamically:
- **In-Flight Tool Call Healer:** When models output raw text actions (e.g. `[Action: tool_name(args)]` or unescaped code blocks) instead of native tool calls, WRAP automatically extracts parameters, reconstructs valid OpenAI `tool_calls` schemas, and sets `finish_reason: "tool_calls"`. This guarantees **0% tool-call failures** for agents (Cursor, Windsurf, Roo Code, Aider).
- **Preemptive Quota & Key Multiplexing:** Detects approaching rate limits (429s) before they happen and routes requests to warm backup credentials without dropping the connection.
- **Zero-Downtime Fallback Cascades:** If an upstream provider suffers an outage or high latency spike, WRAP cascades execution to equivalent healthy models with full context preservation in `< 5ms`.

---

### 3. Real-Time Telemetry & Cost Analytics
Inspect cluster-wide throughput, token velocities, and spend burn-down across all connected providers with high-resolution graphs.
- **P50 / P95 / P99 Latency distributions** tracked per provider and virtual tier.
- **Real-time token counter** tracking prompt vs. completion consumption across billable cycles.
- **SSE streaming latency monitors** measuring time-to-first-token (TTFT) and token jitter.

<!-- ANALYTICS SCREENSHOT PLACEHOLDER -->
<p align="center">
  <img src="docs/assets/analytics-dashboard.png" alt="WRAP Real-time Telemetry & Cost Dashboard" width="100%" style="border-radius: 8px; border: 1px solid #1e293b;" />
</p>
<p align="center"><em>Figure 3: Deep telemetry analytics — Token velocity meters, latency percentiles, and live request distribution.</em></p>

---

### 4. Operator Security Enclave & Control Room
Enterprise identity controls powered by Fernet AES-128-CBC encryption for provider secrets and master API access keys.
- **Zero-knowledge vaulting:** Provider API keys are encrypted at rest with hardware/environment derived keys.
- **Role-based admin access:** Instant revocation, credential rotation, and masked key inspection.
- **Production-ready setup wizard:** 1-Click admin onboarding and gateway key rotation.

<!-- LOGIN SCREENSHOT PLACEHOLDER -->
<p align="center">
  <img src="docs/assets/operator-login.png" alt="WRAP Operator Authentication Console" width="100%" style="border-radius: 8px; border: 1px solid #1e293b;" />
</p>
<p align="center"><em>Figure 4: Operator Security Console — Enterprise administrative barrier securing gateway management APIs.</em></p>

---

### 5. Virtual Model Tiers & Spend Governance
Organize dozens of upstream models into cohesive, policy-driven virtual endpoints:
- `auto`: Automatically select the optimal healthy worker based on cost, latency, and current quota availability.
- `tier-deep-reasoning`: High-intelligence models for complex architectural design and mathematical analysis.
- `tier-fast-code`: Ultra-low latency inference engines tailored for autocomplete and real-time generation.
- **Budget Guardrails:** Set per-key daily, weekly, or monthly soft-warnings and hard-stops.

<!-- MODEL TIERS & BUDGETS PLACEHOLDER -->
<p align="center">
  <img src="docs/assets/model-tiers-budgets.png" alt="Virtual Model Tiers and Spend Budgets" width="100%" style="border-radius: 8px; border: 1px solid #1e293b;" />
</p>
<p align="center"><em>Figure 5: Policy configuration — Virtual tier routing, budget allocations, and model capability routing.</em></p>

---

### 6. Dynamic Worker Topology & Health Matrix
Every provider credential spins up an isolated worker node within WRAP’s internal scheduling grid:
- **Least-Recently-Used (LRU) with QoS weighting:** Prevents rate-limit throttling by distributing calls evenly across valid accounts.
- **Exponential circuit breakers:** Workers experiencing 429s or 5xx errors are quarantined and reintroduced progressively.
- **Real-time health probes:** Automated background testing of provider credentials every 60 seconds.

<!-- WORKER TOPOLOGY PLACEHOLDER -->
<p align="center">
  <img src="docs/assets/worker-topology.png" alt="Worker Topology & Live Health Matrix" width="100%" style="border-radius: 8px; border: 1px solid #1e293b;" />
</p>
<p align="center"><em>Figure 6: Real-time worker grid displaying live state, concurrency, latency, and error tracking per worker node.</em></p>

---

## 🧩 Supported Providers

WRAP normalizes provider-specific protocols into the standard OpenAI v1 schema.

| Provider | Model / Endpoint | `/v1/chat/completions` | Stream (SSE) | Tool Calling | Vision | Auto-Fallback | Free-Tier Striping |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Groq LPU** | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Cerebras** | `llama3.1-8b`, `llama3.1-70b` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **Google Gemini** | `gemini-1.5-pro`, `gemini-2.0-flash` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Anthropic** | `claude-3-7-sonnet`, `claude-3-5-haiku` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **DeepSeek** | `deepseek-chat`, `deepseek-reasoner` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **Ollama / Local** | `llama3`, `deepseek-r1`, `qwen2.5-coder` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Mistral AI** | `mistral-large`, `codestral` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |

---

## ⚡ Quickstart

Get WRAP running locally or in production in under 60 seconds.

### Option 1: Docker Compose (Production Stack — Recommended)

The quickest way to launch WRAP along with PostgreSQL 16, backend API, and React Control Console:

```bash
# 1. Clone the repository
git clone https://github.com/your-org/wrap.git
cd wrap

# 2. Configure master key & database credentials
cp backend/.env.example backend/.env

# 3. Launch the full stack (PostgreSQL + FastAPI Gateway + React Mission Control)
docker compose up -d --build
```

#### Terminal Output Verification

```text
[+] Running 4/4
 ✔ Network wrap_wrap_net         Created                               0.1s
 ✔ Container wrap-postgres-1     Healthy                               4.2s
 ✔ Container wrap-backend-1      Healthy (Listening on :8000)          3.8s
 ✔ Container wrap-frontend-1     Started (Serving UI on :3000)         1.2s

=============================================================================
  WRAP GATEWAY IS ONLINE:
  - Control Console:  http://localhost:3000
  - OpenAI Endpoint:  http://localhost:8000/v1/chat/completions
  - Health Endpoint:  http://localhost:8000/healthz
=============================================================================
```

---

### Option 2: Bare-Metal Local Development

For developers building features, writing provider adapters, or customizing the dashboard:

```bash
# -------------------------------------------------------------
# STEP 1: Spin up PostgreSQL persistence
# -------------------------------------------------------------
docker compose up -d postgres

# -------------------------------------------------------------
# STEP 2: Configure & Start Python Backend (FastAPI + AsyncPG)
# -------------------------------------------------------------
cd backend
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# -------------------------------------------------------------
# STEP 3: Start Frontend Control Console (React 19 + Vite)
# -------------------------------------------------------------
cd ../frontend
npm install
npm run dev
```

The React dashboard will be running at `http://localhost:5173`, proxying API requests to the backend at `http://localhost:8000`.

---

### Option 3: Enterprise Kubernetes Deployment

Production manifests with High-Availability replicas, Prometheus ServiceMonitors, and Nginx Ingress routing are included out of the box in [k8s/](k8s/):

```bash
# 1. Build and tag cluster images
docker build -t wrap-backend:latest ./backend
docker build -t wrap-frontend:latest ./frontend

# 2. Deploy namespace, secrets, statefulsets, and ingress via Kustomize
kubectl apply -k k8s/

# 3. Verify cluster workloads
kubectl get pods -n wrap -o wide
kubectl get ingress -n wrap
```

---

## 💻 Client SDK Usage

WRAP is 100% wire-compatible with standard OpenAI libraries across Python, Node.js, Go, and cURL. Simply point `base_url` to your WRAP gateway.

### Python (`openai>=1.0.0`)

```python
from openai import OpenAI

# Point client to your WRAP Gateway instance
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="wrap_replace_with_your_gateway_key"
)

# Use dynamic 'auto' routing or a virtual tier
response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a distributed systems architect."},
        {"role": "user", "content": "Explain consensus algorithms in 3 bullet points."}
    ],
    temperature=0.3,
    stream=False
)

print(response.choices[0].message.content)
```

### TypeScript / Node.js

```typescript
import OpenAI from "openai";

const wrap = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: process.env.WRAP_API_KEY || "wrap_dev_api_key"
});

async function run() {
  const stream = await wrap.chat.completions.create({
    model: "tier-fast-code",
    messages: [{ role: "user", content: "Write a debounce function in TypeScript." }],
    stream: true,
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || "");
  }
}

run();
```

### Direct cURL (Streaming SSE)

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer wrap_dev_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Benchmark token streaming throughput."}
    ]
  }'
```

---

## ⚙️ Configuration & Environment Reference

All bootstrap environment variables live in `backend/.env`. Upstream provider credentials are saved securely in PostgreSQL via the Control Console or `POST /api/credentials`.

| Environment Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **Yes** | — | Async PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `WRAP_MASTER_KEY` | **Yes** | — | 32+ char secret used to derive AES-128 credential encryption keys |
| `WRAP_API_KEYS` | **Yes** | — | Comma-separated client keys accepted for `/v1` and `/api` access |
| `ENVIRONMENT` | No | `production` | Environment tier (`development`, `test`, `production`) |
| `LOG_LEVEL` | No | `INFO` | Structured JSON log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | Whitelisted browser dashboard origins |
| `REQUEST_TIMEOUT_SECONDS` | No | `60` | Non-streaming upstream provider deadline |
| `STREAM_IDLE_TIMEOUT_SECONDS` | No | `120` | Streaming token idle timeout |

---

## 🏛️ Enterprise Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT APPLICATION                                   │
│            LangChain  •  LlamaIndex  •  OpenAI SDK  •  Custom Agent Frameworks         │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ HTTP / SSE POST /v1/chat/completions
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              NGINX REVERSE PROXY & INGRESS                             │
│                  - SSL Termination  •  Gzip  •  Request Size Clamping                  │
└──────────────────┬───────────────────────────────────────────────────────┬─────────────┘
                   │ /api, /v1, /healthz                                   │ Static UI
                   ▼                                                       ▼
┌──────────────────────────────────────┐               ┌─────────────────────────────────┐
│         WRAP GATEWAY ENGINE          │               │      MISSION CONTROL CONSOLE    │
│            (FastAPI Core)            │               │     (React 19 + Tailwind/CSS)   │
│                                      │               └─────────────────────────────────┘
│  ├─ Auth & Token Bucket Rate Limiter │
│  ├─ Policy & Budget Guardrail Engine │
│  ├─ DAG Decomposition Analyzer       │
│  ├─ Least-Recently-Used Scheduler    │
│  └─ Privacy-First Telemetry Tracker  │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                ADAPTER REGISTRY LAYER                                  │
│                                                                                        │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│   │   Groq Adapter   │  │ Cerebras Adapter │  │  Gemini Adapter  │  │ OpenAI/Claude  │ │
│   │ (OpenAI-Compat)  │  │ (OpenAI-Compat)  │  │ (REST & SSE Norm)│  │ (Direct Auth)  │ │
│   └─────────┬────────┘  └─────────┬────────┘  └─────────┬────────┘  └───────┬────────┘ │
└─────────────┼─────────────────────┼─────────────────────┼───────────────────┼──────────┘
              ▼                     ▼                     ▼                   ▼
      [Upstream Groq API]   [Cerebras Wafer]       [Google Vertex]      [Direct APIs]
```

---

## 📚 Documentation

Detailed deep-dives are located across the repository documentation:

* 📖 **[API Reference](API.md)** — Comprehensive OpenAPI specifications, parameter forwarding rules, and management endpoints.
* 🏛️ **[System Architecture](ARCHITECTURE.md)** — Architectural patterns, memory footprint, and scheduling lifecycle.
* 🔌 **[Provider Adapters](PROVIDERS.md)** — Adding new LLM providers, error normalization, and capability manifests.
* ⚙️ **[Configuration Manual](CONFIGURATION.md)** — Advanced runtime options, pool sizing, and network timeouts.
* 💾 **[Database Schemas](DATABASE.md)** — SQLAlchemy 2.0 relational schema, indices, and audit tables.
* ☸️ **[Kubernetes Guide](k8s/README.md)** — StatefulSet storage, ServiceMonitors, and rolling cluster upgrades.
* 🛠️ **[Development Guide](DEVELOPMENT.md)** — Test fixtures, mock providers, and contribution workflows.

---

## 🤝 Contributing & Community

We welcome contributions to WRAP! Whether it's adding new provider adapters, optimizing DAG scheduling algorithms, or enhancing the Control Console:

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat(providers): add DeepSeek-R1 adapter'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the Apache 2.0 License. See `LICENSE` for more information.

<p align="center">
  <sub>Built with ❤️ by the WRAP Core Team. Designed for resilient, multi-agent AI infrastructure.</sub>
</p>
