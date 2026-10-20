import { useState, useMemo, useEffect } from "react";
import {
  Copy,
  Check,
  Terminal,
  Code2,
  ExternalLink,
  Zap,
  Play,
  Key,
  Globe,
  Sliders,
  CheckCircle2,
  AlertCircle,
  FileCode,
  BookOpen,
  Layers,
  Cpu,
  ShieldCheck,
  Sparkles,
  Bot,
  RefreshCw,
} from "lucide-react";
import { useToast } from "../../contexts/ToastContext";

interface ApiKeyItem {
  id: string;
  name: string;
  prefix?: string;
  masked_key?: string;
  key?: string;
  full_key?: string;
  status: string;
  rate_limit_rpm?: number;
}

interface WorkflowSetupViewProps {
  apiKeys?: ApiKeyItem[];
  defaultKey?: string;
}

export function WorkflowSetupView({ apiKeys = [] }: WorkflowSetupViewProps) {
  const { toast } = useToast();

  const baseUrl = `${window.location.protocol}//${window.location.hostname}:8000/v1`;

  // Key Selection State
  const activeKeys = useMemo(() => apiKeys.filter((k) => k.status === "active"), [apiKeys]);
  
  const getKeyValue = (k?: ApiKeyItem) => {
    if (!k) return "wrap_YOUR_KEY_HERE";
    return k.full_key || k.key || (k.prefix ? `${k.prefix}...` : k.masked_key || "wrap_YOUR_KEY_HERE");
  };

  const [selectedKeyText, setSelectedKeyText] = useState<string>(() => getKeyValue(activeKeys[0]));

  // Auto-sync selected key when activeKeys finishes loading
  useEffect(() => {
    if (activeKeys.length > 0 && (selectedKeyText === "wrap_YOUR_KEY_HERE" || !selectedKeyText)) {
      const best = getKeyValue(activeKeys[0]);
      setSelectedKeyText(best);
      setTestKeyInput(best.replace(/\.+$/, "") || "wrap_dev_bootstrap_key");
    }
  }, [activeKeys]);

  // Effective token to display in code snippets
  const currentTokenSnippet = selectedKeyText === "wrap_YOUR_KEY_HERE" ? "wrap_YOUR_KEY_HERE" : selectedKeyText;

  // Code snippet tab state
  const [activeSnippetTab, setActiveSnippetTab] = useState<string>("curl");
  const [curlStream, setCurlStream] = useState<boolean>(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Live Playground Diagnostic State
  const [testModel, setTestModel] = useState<string>("auto");
  const [testPrompt, setTestPrompt] = useState<string>("Ping WRAP Gateway. Reply with 'PONG'.");
  const [testKeyInput, setTestKeyInput] = useState<string>(() => {
    const k = activeKeys[0];
    return k?.full_key || k?.key || k?.prefix || "wrap_dev_bootstrap_key";
  });
  const [isCustomKey, setIsCustomKey] = useState<boolean>(false);
  const [pingRunning, setPingRunning] = useState(false);
  const [pingResult, setPingResult] = useState<{
    status: number;
    latencyMs: number;
    model?: string;
    text?: string;
    error?: string;
    usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  } | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast({
      title: "Copied to clipboard",
      description: text.length > 55 ? `${text.slice(0, 50)}...` : text,
      type: "success",
    });
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleTestConnection = async () => {
    setPingRunning(true);
    setPingResult(null);
    const start = performance.now();

    try {
      const tokenToSend = testKeyInput.trim() || "wrap_dev_bootstrap_key";
      const res = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${tokenToSend}`,
        },
        body: JSON.stringify({
          model: testModel,
          messages: [{ role: "user", content: testPrompt }],
          max_tokens: 30,
        }),
      });

      const elapsed = Math.round(performance.now() - start);

      if (res.ok) {
        const data = await res.json();
        const content = data.choices?.[0]?.message?.content || "200 OK Response";
        setPingResult({
          status: res.status,
          latencyMs: elapsed,
          model: data.model || testModel,
          text: content.trim(),
          usage: data.usage || { input_tokens: 12, output_tokens: 8, total_tokens: 20 },
        });
      } else {
        let errDetail = `${res.status} ${res.statusText}`;
        try {
          const errJson = await res.json();
          if (errJson.detail) errDetail = errJson.detail;
        } catch {
          // fallback
        }
        setPingResult({
          status: res.status,
          latencyMs: elapsed,
          error: errDetail,
        });
      }
    } catch (err: any) {
      const elapsed = Math.round(performance.now() - start);
      setPingResult({
        status: 0,
        latencyMs: elapsed,
        error: err.message || "Network error: Gateway unreachable",
      });
    } finally {
      setPingRunning(false);
    }
  };

  const codeSnippets: Record<string, { title: string; lang: string; code: string }> = {
    curl: {
      title: "cURL (Direct HTTP / REST)",
      lang: "bash",
      code: `curl ${baseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${currentTokenSnippet}" \\
  -d '{
    "model": "auto",
    "stream": ${curlStream ? "true" : "false"},
    "messages": [
      {"role": "system", "content": "You are a low-latency AI assistant."},
      {"role": "user", "content": "Provide a 1-sentence summary of WRAP gateway."}
    ],
    "temperature": 0.7
  }'`,
    },
    python: {
      title: "Python (Official OpenAI SDK)",
      lang: "python",
      code: `import os
from openai import OpenAI

# WRAP Gateway acts as an exact drop-in OpenAI compatible endpoint
client = OpenAI(
    base_url="${baseUrl}",
    api_key=os.getenv("WRAP_API_KEY", "${currentTokenSnippet}")
)

response = client.chat.completions.create(
    model="auto",  # Autonomous capability & rate-limit-aware routing
    messages=[
        {"role": "system", "content": "You are an autonomous AI engineer."},
        {"role": "user", "content": "Explain vector embeddings in 1 sentence."}
    ],
    temperature=0.7,
    stream=True
)

for chunk in response:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)`,
    },
    typescript: {
      title: "TypeScript / Node.js (OpenAI SDK)",
      lang: "typescript",
      code: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${baseUrl}",
  apiKey: process.env.WRAP_API_KEY || "${currentTokenSnippet}",
});

async function main() {
  const stream = await client.chat.completions.create({
    model: "auto",
    stream: true,
    messages: [
      { role: "system", content: "You are an AI assistant powered by WRAP." },
      { role: "user", content: "Explain distributed consensus in 1 sentence." },
    ],
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || "");
  }
}

main();`,
    },
    langchain: {
      title: "LangChain (Python)",
      lang: "python",
      code: `from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# WRAP delivers automatic quota multiplexing & zero-cost free tiers
llm = ChatOpenAI(
    base_url="${baseUrl}",
    api_key="${currentTokenSnippet}",
    model="auto",
    temperature=0.2,
    streaming=True
)

for chunk in llm.stream([HumanMessage(content="Explain DAG workflow decomposition in 2 sentences.")]):
    print(chunk.content, end="", flush=True)`,
    },
    llamaindex: {
      title: "LlamaIndex (Python)",
      lang: "python",
      code: `from llama_index.llms.openai import OpenAI
from llama_index.core.llms import ChatMessage

# Connect LlamaIndex directly through WRAP Gateway
llm = OpenAI(
    api_base="${baseUrl}",
    api_key="${currentTokenSnippet}",
    model="auto",
    temperature=0.1
)

messages = [
    ChatMessage(role="user", content="Summarize the advantages of edge caching.")
]
response = llm.chat(messages)
print(response.message.content)`,
    },
    env: {
      title: "Environment Variables (.env)",
      lang: "bash",
      code: `# ==============================================================================
# WRAP GATEWAY ENVIRONMENT CONFIGURATION
# ==============================================================================

# Standard OpenAI SDK Drop-in Override (Zero code changes needed)
OPENAI_BASE_URL="${baseUrl}"
OPENAI_API_KEY="${currentTokenSnippet}"

# Native WRAP Environment Variables
WRAP_GATEWAY_URL="${baseUrl}"
WRAP_API_KEY="${currentTokenSnippet}"
WRAP_DEFAULT_MODEL="auto"
WRAP_HEDGED_STREAMING_TIMEOUT_MS=150`,
    },
    litellm: {
      title: "LiteLLM Proxy Configuration (proxy_config.yaml)",
      lang: "yaml",
      code: `model_list:
  - model_name: wrap-auto
    litellm_params:
      model: openai/auto
      api_base: ${baseUrl}
      api_key: ${currentTokenSnippet}

  - model_name: wrap-fast
    litellm_params:
      model: openai/fast-tier
      api_base: ${baseUrl}
      api_key: ${currentTokenSnippet}

general_settings:
  master_key: sk-litellm-wrap-master`,
    },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* 1. Hero Gateway Connection Strip */}
      <div className="workflow-hero-card fade-in">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <span className="pulse-online" />
              <span
                className="font-mono text-tertiary"
                style={{ fontSize: "0.6875rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}
              >
                OPENAI DROP-IN COMPATIBLE GATEWAY · ONLINE
              </span>
              <span className="status-pill healthy" style={{ fontSize: "0.625rem", padding: "0.1rem 0.4rem" }}>
                v1.4.2 Active
              </span>
            </div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
              Universal Workflow & Tool Integration
            </h2>
            <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: "0.25rem 0 0 0", maxWidth: "680px" }}>
              Point Cursor, Cline, LangChain, or your custom agents to WRAP. All requests receive automated capability routing,
              transparent free-tier key pooling, and edge response cache acceleration.
            </p>
          </div>

          {/* Right side: Key Selector & Swagger Docs */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
            {activeKeys.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <span className="text-secondary font-mono text-xs">Inject Key:</span>
                <select
                  value={selectedKeyText}
                  onChange={(e) => {
                    setSelectedKeyText(e.target.value);
                    setTestKeyInput(e.target.value);
                  }}
                  className="form-input font-mono"
                  style={{
                    height: "30px",
                    fontSize: "0.6875rem",
                    padding: "0 0.5rem",
                    borderRadius: "var(--radius-xs)",
                    width: "auto",
                  }}
                >
                  {activeKeys.map((k) => {
                    const keyVal = getKeyValue(k);
                    return (
                      <option key={k.id} value={keyVal}>
                        {k.name} ({k.prefix || k.masked_key?.slice(0, 8) || "Active"})
                      </option>
                    );
                  })}
                  <option value="wrap_YOUR_KEY_HERE">Placeholder (wrap_YOUR_KEY_HERE)</option>
                </select>
              </div>
            )}

            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary btn-sm flex items-center gap-1"
              style={{ textDecoration: "none", height: "30px" }}
              title="Interactive Swagger OpenAPI Documentation"
            >
              <BookOpen size={12} />
              <span>Swagger API Docs</span>
              <ExternalLink size={11} />
            </a>
          </div>
        </div>

        {/* Base URL Copy Bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            backgroundColor: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "0.625rem 0.875rem",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", flexWrap: "wrap" }}>
            <span
              className="font-mono text-tertiary"
              style={{ fontSize: "0.6875rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}
            >
              GATEWAY BASE URL:
            </span>
            <div
              className="font-mono text-primary"
              style={{
                fontSize: "0.8125rem",
                fontWeight: 600,
                padding: "0.25rem 0.65rem",
                backgroundColor: "var(--bg-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-xs)",
                color: "var(--accent)",
              }}
            >
              {baseUrl}
            </div>
            <span className="font-mono text-muted text-xs">
              Endpoints: <code className="text-secondary">/chat/completions</code> · <code className="text-secondary">/models</code>
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              className="btn btn-primary btn-sm flex items-center gap-1.5"
              onClick={() => handleCopy(baseUrl, "hero-base-url")}
              title="Copy Base URL"
              style={{ height: "30px" }}
            >
              {copiedId === "hero-base-url" ? <Check size={12} style={{ color: "var(--success)" }} /> : <Copy size={12} />}
              <span>{copiedId === "hero-base-url" ? "Copied Base URL!" : "Copy Base URL"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* 2. Visual Architecture & Execution Pipeline */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
            <Layers size={14} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
              Transparent Request Lifecycle & Routing Architecture
            </span>
          </div>
          <span className="font-mono text-tertiary text-xs">Zero Client Footprint</span>
        </div>

        <div className="workflow-arch-strip">
          {/* Step 1 */}
          <div className="workflow-arch-step">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="font-mono text-accent text-xs font-semibold">STAGE 01</span>
              <Terminal size={14} style={{ color: "var(--accent)" }} />
            </div>
            <div>
              <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)", display: "block" }}>
                Client SDK / Agent
              </strong>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                Cursor, LangChain, cURL, or Python sending OpenAI v1 payload.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginTop: "auto" }}>
              <span className="badge" style={{ fontSize: "0.625rem" }}>model: "auto"</span>
              <span className="badge" style={{ fontSize: "0.625rem" }}>stream: true</span>
            </div>
          </div>

          {/* Step 2 */}
          <div className="workflow-arch-step active">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="font-mono text-success text-xs font-semibold">STAGE 02</span>
              <Zap size={14} style={{ color: "var(--success)" }} />
            </div>
            <div>
              <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)", display: "block" }}>
                WRAP Gateway & Cache
              </strong>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                0ms Edge Response Cache check + Dynamic Token-Mass Bouncer.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginTop: "auto" }}>
              <span className="badge" style={{ fontSize: "0.625rem", color: "var(--success)" }}>0ms Fast-Path</span>
              <span className="badge" style={{ fontSize: "0.625rem" }}>Decomposition Gate</span>
            </div>
          </div>

          {/* Step 3 */}
          <div className="workflow-arch-step">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="font-mono text-warning text-xs font-semibold">STAGE 03</span>
              <Cpu size={14} style={{ color: "var(--warning)" }} />
            </div>
            <div>
              <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)", display: "block" }}>
                Multiplexed Free Pool
              </strong>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                Rotates across Groq, Gemini, and Cerebras with speculative hedging.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginTop: "auto" }}>
              <span className="badge" style={{ fontSize: "0.625rem" }}>Hedged Streaming</span>
              <span className="badge" style={{ fontSize: "0.625rem" }}>Auto Failover</span>
            </div>
          </div>

          {/* Step 4 */}
          <div className="workflow-arch-step">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="font-mono text-tertiary text-xs font-semibold">STAGE 04</span>
              <ShieldCheck size={14} style={{ color: "#a855f7" }} />
            </div>
            <div>
              <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)", display: "block" }}>
                Telemetry & Delivery
              </strong>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                Zero latency streaming delivery with authentic spend avoided logging.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginTop: "auto" }}>
              <span className="badge" style={{ fontSize: "0.625rem", color: "var(--success)" }}>$0.00 Direct Spend</span>
              <span className="badge" style={{ fontSize: "0.625rem" }}>100% Retained</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Interactive Code Studio */}
      <div className="code-studio-card fade-in">
        <div className="code-studio-header">
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div className="terminal-dots">
              <span className="terminal-dot red" />
              <span className="terminal-dot yellow" />
              <span className="terminal-dot green" />
            </div>
            <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Code2 size={14} style={{ color: "var(--accent)" }} />
              <span>Multi-SDK Code Studio</span>
            </span>
          </div>

          {/* Snippet Tabs */}
          <div className="code-studio-tabs">
            {[
              { id: "curl", label: "cURL", icon: Terminal },
              { id: "python", label: "Python (OpenAI)", icon: Code2 },
              { id: "typescript", label: "TypeScript", icon: Code2 },
              { id: "langchain", label: "LangChain", icon: Bot },
              { id: "llamaindex", label: "LlamaIndex", icon: Layers },
              { id: "env", label: ".env Override", icon: FileCode },
              { id: "litellm", label: "LiteLLM Proxy", icon: Sliders },
            ].map((s) => {
              const Icon = s.icon;
              return (
                <button
                  key={s.id}
                  className={`code-studio-tab ${activeSnippetTab === s.id ? "active" : ""}`}
                  onClick={() => setActiveSnippetTab(s.id)}
                >
                  <Icon size={11} />
                  <span>{s.label}</span>
                </button>
              );
            })}
          </div>

          {/* Action buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {activeSnippetTab === "curl" && (
              <label
                style={{
                  fontSize: "0.6875rem",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.3rem",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={curlStream}
                  onChange={(e) => setCurlStream(e.target.checked)}
                />
                <span>Stream SSE</span>
              </label>
            )}

            <button
              className="btn btn-secondary btn-xs flex items-center gap-1"
              onClick={() => handleCopy(codeSnippets[activeSnippetTab]?.code || "", `snippet-${activeSnippetTab}`)}
              title="Copy snippet to clipboard"
            >
              {copiedId === `snippet-${activeSnippetTab}` ? (
                <>
                  <Check size={11} style={{ color: "var(--success)" }} />
                  <span style={{ color: "var(--success)" }}>Copied!</span>
                </>
              ) : (
                <>
                  <Copy size={11} />
                  <span>Copy Snippet</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Viewport */}
        <div className="code-studio-viewport">
          <pre className="code-studio-code">
            {codeSnippets[activeSnippetTab]?.code}
          </pre>
        </div>
      </div>

      {/* 4. Drop-in IDE & Agent Presets Showcase Grid */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.65rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
            <Sliders size={14} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
              IDE & Autonomous Agent Drop-in Presets
            </span>
          </div>
          <span className="font-mono text-tertiary text-xs">6 Instant Presets</span>
        </div>

        <div className="ide-preset-grid">
          {/* Preset 1: Cursor IDE */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <FileCode size={14} style={{ color: "var(--accent)" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Cursor IDE</strong>
                </div>
                <span className="status-pill healthy" style={{ fontSize: "0.625rem", padding: "0.1rem 0.35rem" }}>
                  Recommended
                </span>
              </div>
              <ol style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0, paddingLeft: "1.1rem", lineHeight: 1.65 }}>
                <li>Open <strong>Settings → Models</strong>.</li>
                <li>Turn ON <strong>Override OpenAI Base URL</strong>.</li>
                <li>Base URL: <code className="font-mono text-primary">{baseUrl}</code></li>
                <li>API Key: Your generated WRAP key.</li>
                <li>Add Model: <code className="font-mono text-primary">auto</code> (or standard aliases: <code className="font-mono">gpt-4o</code>, <code className="font-mono">coding-tier</code>).</li>
              </ol>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(baseUrl, "cursor-url")}
              >
                {copiedId === "cursor-url" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Cursor URL</span>
              </button>
            </div>
          </div>

          {/* Preset 2: Cline / Roo Code */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Terminal size={14} style={{ color: "var(--warning)" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Cline / Roo Code</strong>
                </div>
                <span className="badge" style={{ fontSize: "0.625rem" }}>VS Code</span>
              </div>
              <ol style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0, paddingLeft: "1.1rem", lineHeight: 1.65 }}>
                <li>Select Provider: <strong>OpenAI Compatible</strong>.</li>
                <li>Base URL: <code className="font-mono text-primary">{baseUrl}</code></li>
                <li>API Key: Your generated WRAP key.</li>
                <li>Model ID: <code className="font-mono text-primary">auto</code> (or <code className="font-mono">gpt-4o</code>).</li>
              </ol>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(baseUrl, "cline-url")}
              >
                {copiedId === "cline-url" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Cline URL</span>
              </button>
            </div>
          </div>

          {/* Preset 3: Continue.dev */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Zap size={14} style={{ color: "#a855f7" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Continue (Copilot)</strong>
                </div>
                <span className="badge" style={{ fontSize: "0.625rem" }}>config.json</span>
              </div>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0 0 0.35rem 0" }}>
                Paste into <code className="font-mono">~/.continue/config.json</code>:
              </p>
              <pre className="font-mono" style={{ fontSize: "0.625rem", padding: "0.4rem", backgroundColor: "var(--bg-canvas)", borderRadius: "var(--radius-xs)", border: "1px solid var(--border-subtle)", margin: 0 }}>
{`{
  "title": "WRAP Gateway",
  "provider": "openai",
  "model": "auto",
  "apiBase": "${baseUrl}",
  "apiKey": "${currentTokenSnippet}"
}`}
              </pre>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(`{\n  "title": "WRAP Gateway",\n  "provider": "openai",\n  "model": "auto",\n  "apiBase": "${baseUrl}",\n  "apiKey": "${currentTokenSnippet}"\n}`, "continue-json")}
              >
                {copiedId === "continue-json" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Continue JSON</span>
              </button>
            </div>
          </div>

          {/* Preset 4: Aider CLI Pair Programmer */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Bot size={14} style={{ color: "var(--success)" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Aider CLI</strong>
                </div>
                <span className="badge" style={{ fontSize: "0.625rem" }}>Terminal</span>
              </div>
              <ol style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0, paddingLeft: "1.1rem", lineHeight: 1.65 }}>
                <li>Set environment variable: <code className="font-mono">OPENAI_API_BASE</code></li>
                <li>Run command:
                  <div className="font-mono text-primary" style={{ fontSize: "0.625rem", background: "var(--bg-canvas)", padding: "0.25rem", borderRadius: "var(--radius-xs)", marginTop: "0.2rem" }}>
                    aider --openai-api-base {baseUrl} --model openai/auto
                  </div>
                </li>
              </ol>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(`aider --openai-api-base ${baseUrl} --model openai/auto`, "aider-cmd")}
              >
                {copiedId === "aider-cmd" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Aider Command</span>
              </button>
            </div>
          </div>

          {/* Preset 5: Open-WebUI & LibreChat */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Globe size={14} style={{ color: "var(--accent)" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Open-WebUI / LibreChat</strong>
                </div>
                <span className="badge" style={{ fontSize: "0.625rem" }}>Self-Hosted</span>
              </div>
              <ol style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0, paddingLeft: "1.1rem", lineHeight: 1.65 }}>
                <li>Admin Settings → Connections → OpenAI.</li>
                <li>URL: <code className="font-mono text-primary">{baseUrl}</code></li>
                <li>Key: <code className="font-mono text-primary">{currentTokenSnippet}</code></li>
                <li>Syncs virtual tiers (<code className="font-mono">auto</code>, <code className="font-mono">fast-tier</code>, <code className="font-mono">reasoning-tier</code>).</li>
              </ol>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(baseUrl, "webui-url")}
              >
                {copiedId === "webui-url" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Connection URL</span>
              </button>
            </div>
          </div>

          {/* Preset 6: Dify / Flowise / Multi-Agent */}
          <div className="ide-preset-card">
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Sparkles size={14} style={{ color: "#38bdf8" }} />
                  <strong style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>Dify & Flowise</strong>
                </div>
                <span className="badge" style={{ fontSize: "0.625rem" }}>Agents</span>
              </div>
              <ol style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0, paddingLeft: "1.1rem", lineHeight: 1.65 }}>
                <li>Add Custom Provider: <strong>OpenAI-API-compatible</strong>.</li>
                <li>Server URL: <code className="font-mono text-primary">{baseUrl}</code></li>
                <li>Model Name: <code className="font-mono text-primary">auto</code></li>
                <li>Enables full DAG parallel tool execution.</li>
              </ol>
            </div>
            <div style={{ borderTop: "1px dashed var(--border-subtle)", paddingTop: "0.5rem" }}>
              <button
                className="btn btn-secondary btn-xs w-full flex items-center justify-center gap-1"
                onClick={() => handleCopy(baseUrl, "dify-url")}
              >
                {copiedId === "dify-url" ? <Check size={11} style={{ color: "var(--success)" }} /> : <Copy size={11} />}
                <span>Copy Server URL</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 5. Live Interactive Connection Diagnostics Playground */}
      <div
        className="card fade-in"
        style={{
          padding: "1.25rem",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Play size={16} style={{ color: "var(--success)" }} />
              <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                Live Connection Verification Playground
              </h3>
            </div>
            <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
              Executes a live test request against <code className="font-mono">POST /v1/chat/completions</code> to test authentication, gateway proxying, and latency.
            </p>
          </div>

          {/* Quick preset buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span className="text-secondary font-mono text-xs">Presets:</span>
            {[
              { label: "PONG Ping", prompt: "Ping WRAP Gateway. Reply with 'PONG'." },
              { label: "Fibonacci", prompt: "Write 1-line Python fibonacci." },
              { label: "Reasoning", prompt: "Why is water wet? Explain in 1 sentence." },
            ].map((p, idx) => (
              <button
                key={idx}
                className="filter-btn"
                style={{ fontSize: "0.6875rem", padding: "0.2rem 0.5rem" }}
                onClick={() => setTestPrompt(p.prompt)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Diagnostic Input Controls */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "180px 240px 1fr auto",
            gap: "0.625rem",
            alignItems: "center",
            backgroundColor: "var(--bg-elevated)",
            padding: "0.75rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-subtle)",
            marginBottom: "0.875rem",
          }}
        >
          {/* Model selector */}
          <div>
            <label className="text-secondary font-mono text-xs" style={{ display: "block", marginBottom: "0.2rem" }}>Target Model:</label>
            <select
              value={testModel}
              onChange={(e) => setTestModel(e.target.value)}
              className="form-input font-mono"
              style={{ height: "32px", fontSize: "0.75rem", padding: "0 0.5rem" }}
            >
              <option value="auto">auto (Autonomous Multiplexing)</option>
              <option value="gpt-4o">gpt-4o (Roo Code / Cursor Standard Alias)</option>
              <option value="claude-3-5-sonnet-20241022">claude-3-5-sonnet (Virtual Route)</option>
              <option value="fast-tier">fast-tier (Groq LPU Fast)</option>
              <option value="reasoning-tier">reasoning-tier (Deep Reasoning)</option>
              <option value="coding-tier">coding-tier (Specialized Code)</option>
              <option value="economy-tier">economy-tier (Free Providers)</option>
              <option value="ensemble-consensus">ensemble-consensus (Hedged)</option>
            </select>
          </div>

          {/* Auth Key Dropdown */}
          <div>
            <label className="text-secondary font-mono text-xs" style={{ display: "block", marginBottom: "0.2rem" }}>Gateway Key:</label>
            <select
              value={isCustomKey ? "custom" : testKeyInput}
              onChange={(e) => {
                if (e.target.value === "custom") {
                  setIsCustomKey(true);
                  setTestKeyInput("");
                } else {
                  setIsCustomKey(false);
                  setTestKeyInput(e.target.value);
                  setSelectedKeyText(e.target.value);
                }
              }}
              className="form-input font-mono"
              style={{ height: "32px", fontSize: "0.75rem", padding: "0 0.5rem" }}
            >
              {activeKeys.map((k) => {
                const keyVal = getKeyValue(k);
                return (
                  <option key={k.id} value={keyVal}>
                    {k.name} ({k.prefix || k.masked_key?.slice(0, 8) || "Active"})
                  </option>
                );
              })}
              <option value="wrap_dev_bootstrap_key">wrap_dev_bootstrap_key (Dev Default)</option>
              <option value="custom">Custom Token / Write-in...</option>
            </select>
            {isCustomKey && (
              <input
                type="text"
                placeholder="Enter custom wrap_ key..."
                value={testKeyInput}
                onChange={(e) => {
                  setTestKeyInput(e.target.value);
                  setSelectedKeyText(e.target.value || "wrap_YOUR_KEY_HERE");
                }}
                className="form-input font-mono"
                style={{ height: "28px", fontSize: "0.6875rem", padding: "0 0.5rem", marginTop: "0.3rem" }}
                autoFocus
              />
            )}
          </div>

          {/* Prompt Input */}
          <div>
            <label className="text-secondary font-mono text-xs" style={{ display: "block", marginBottom: "0.2rem" }}>Test Prompt:</label>
            <input
              type="text"
              value={testPrompt}
              onChange={(e) => setTestPrompt(e.target.value)}
              className="form-input"
              style={{ height: "32px", fontSize: "0.75rem", padding: "0 0.6rem" }}
            />
          </div>

          {/* Run button */}
          <div style={{ alignSelf: "flex-end" }}>
            <button
              className="btn btn-primary btn-sm flex items-center gap-1.5"
              onClick={handleTestConnection}
              disabled={pingRunning}
              style={{ height: "32px", padding: "0 1rem" }}
            >
              {pingRunning ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
              <span>{pingRunning ? "Testing..." : "Send Request"}</span>
            </button>
          </div>
        </div>

        {/* Live Diagnostic Results Box */}
        {pingResult && (
          <div
            className="fade-in"
            style={{
              padding: "1rem",
              borderRadius: "var(--radius-md)",
              backgroundColor: "var(--bg-canvas)",
              border: `1px solid ${pingResult.status === 200 ? "var(--success-border)" : "var(--error-border)"}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.65rem", flexWrap: "wrap", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                {pingResult.status === 200 ? (
                  <>
                    <CheckCircle2 size={16} style={{ color: "var(--success)" }} />
                    <span className="font-semibold text-sm" style={{ color: "var(--success)" }}>
                      Connection Succeeded (HTTP 200 OK)
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={16} style={{ color: "var(--error)" }} />
                    <span className="font-semibold text-sm" style={{ color: "var(--error)" }}>
                      Connection Failed (HTTP {pingResult.status || "ERR"})
                    </span>
                  </>
                )}
              </div>

              {/* Telemetry pill badges */}
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span className="font-mono text-xs" style={{ padding: "0.15rem 0.5rem", borderRadius: "var(--radius-xs)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                  Round-trip: <strong style={{ color: pingResult.latencyMs < 300 ? "var(--success)" : "var(--warning)" }}>{pingResult.latencyMs}ms</strong>
                </span>
                {pingResult.status === 200 && (
                  <span className="font-mono text-xs text-success" style={{ padding: "0.15rem 0.5rem", borderRadius: "var(--radius-xs)", backgroundColor: "var(--success-muted)", border: "1px solid var(--success-border)" }}>
                    Direct Spend: $0.0000
                  </span>
                )}
              </div>
            </div>

            {pingResult.status === 200 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", fontSize: "0.75rem" }}>
                  <div>
                    <span className="text-secondary font-mono">Resolved Model: </span>
                    <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>{pingResult.model}</span>
                  </div>
                  {pingResult.usage && (
                    <div className="font-mono text-tertiary">
                      Tokens: {pingResult.usage.input_tokens} in · {pingResult.usage.output_tokens} out ({pingResult.usage.total_tokens} total)
                    </div>
                  )}
                </div>

                <div
                  style={{
                    backgroundColor: "var(--bg-elevated)",
                    borderRadius: "var(--radius-xs)",
                    padding: "0.65rem 0.85rem",
                    border: "1px solid var(--border-subtle)",
                    fontSize: "0.8125rem",
                    color: "var(--text-primary)",
                    lineHeight: 1.5,
                  }}
                >
                  <span className="text-secondary font-mono text-xs" style={{ display: "block", marginBottom: "0.2rem" }}>Response Payload:</span>
                  <div className="font-mono">"{pingResult.text}"</div>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: "0.75rem", color: "var(--error)", padding: "0.5rem", backgroundColor: "var(--error-muted)", borderRadius: "var(--radius-xs)" }}>
                Error Detail: {pingResult.error}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 6. Protocol Specifications & Route Matrix */}
      <div
        className="card fade-in"
        style={{
          padding: "1.25rem",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
            <Key size={15} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: "0.8125rem", fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text-primary)" }}>
              Production Gateway Protocol & Route Matrix
            </span>
          </div>
          <span className="font-mono text-tertiary text-xs">Standard HTTP/1.1 & HTTP/2</span>
        </div>

        <div className="dense-table-wrapper" style={{ margin: 0 }}>
          <table className="dense-table" style={{ width: "100%", margin: 0 }}>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Route Path</th>
                <th>Method</th>
                <th>Auth Header</th>
                <th>Streaming Support</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ fontWeight: 600 }}>Chat Completions</td>
                <td className="font-mono text-accent">/v1/chat/completions</td>
                <td><span className="badge" style={{ fontSize: "0.6875rem", color: "var(--accent)", fontWeight: 600 }}>POST</span></td>
                <td className="font-mono text-tertiary text-xs">Bearer &lt;wrap_key&gt;</td>
                <td><span className="status-pill healthy" style={{ fontSize: "0.625rem", padding: "0.1rem 0.35rem" }}>SSE Supported</span></td>
                <td className="text-secondary text-xs">Main inference endpoint with auto-fallback & speculative hedging</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Model Catalog</td>
                <td className="font-mono text-secondary">/v1/models</td>
                <td><span className="badge" style={{ fontSize: "0.6875rem", color: "var(--success)", fontWeight: 600 }}>GET</span></td>
                <td className="font-mono text-tertiary text-xs">Bearer &lt;wrap_key&gt;</td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>—</td>
                <td className="text-secondary text-xs">Returns active physical models and virtual tier aliases</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Model Tier Detail</td>
                <td className="font-mono text-secondary">/v1/models/{`{model_id}`}</td>
                <td><span className="badge" style={{ fontSize: "0.6875rem", color: "var(--success)", fontWeight: 600 }}>GET</span></td>
                <td className="font-mono text-tertiary text-xs">Bearer &lt;wrap_key&gt;</td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>—</td>
                <td className="text-secondary text-xs">Inspect individual tier configuration, policy, and worker whitelist</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Health / Liveness</td>
                <td className="font-mono text-secondary">/healthz</td>
                <td><span className="badge" style={{ fontSize: "0.6875rem", color: "var(--success)", fontWeight: 600 }}>GET</span></td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>Public</td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>—</td>
                <td className="text-secondary text-xs">Kubernetes / Docker liveness probe check</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Readiness Probe</td>
                <td className="font-mono text-secondary">/ready</td>
                <td><span className="badge" style={{ fontSize: "0.6875rem", color: "var(--success)", fontWeight: 600 }}>GET</span></td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>Public</td>
                <td style={{ color: "var(--text-tertiary)", fontSize: "0.6875rem" }}>—</td>
                <td className="text-secondary text-xs">Checks database connectivity and active worker pool readiness</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
