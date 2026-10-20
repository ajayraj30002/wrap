import { useState, useEffect, useMemo, useCallback } from "react";
import { Search, RefreshCw, Filter, Layers } from "lucide-react";
import { RequestDrawer, type RequestDetailData } from "../components/ui/RequestDrawer";
import { apiClient } from "../lib/apiClient";
import { formatShortRequestId, formatExecutedModelBadge, parseProviderInfo } from "../lib/providerBadges";

export function Requests() {
  const [requests, setRequests] = useState<RequestDetailData[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<"ALL" | "DAG" | "SINGLE">("ALL");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "completed" | "failed">("ALL");
  const [selectedRequest, setSelectedRequest] = useState<RequestDetailData | null>(null);

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    try {
      const [reqRes, decRes, wkRes] = await Promise.allSettled([
        apiClient.get("/api/metrics/requests?page_size=50"),
        apiClient.get("/api/routing/decisions"),
        apiClient.get("/api/workers"),
      ]);

      const decisionsMap = new Map<string, any>();
      if (decRes.status === "fulfilled" && Array.isArray(decRes.value)) {
        for (const dec of decRes.value) {
          decisionsMap.set(dec.request_id, dec);
        }
      }

      const workersMap = new Map<string, any>();
      if (wkRes.status === "fulfilled" && Array.isArray(wkRes.value)) {
        for (const w of wkRes.value) {
          workersMap.set(w.id, w);
        }
      }

      if (reqRes.status === "fulfilled" && reqRes.value?.items && reqRes.value.items.length > 0) {
        const mapped: RequestDetailData[] = reqRes.value.items.map((it: any) => {
          const dec = decisionsMap.get(it.request_id);
          const matchedWorker = workersMap.get(it.worker_id) || workersMap.get(dec?.selected_worker);
          const executedModel = matchedWorker?.model || (it.model === "auto" ? "groq/compound-mini" : it.model);

          const inTok = it.input_tokens || 0;
          const outTok = it.output_tokens || 0;
          const totTok = it.total_tokens || (inTok + outTok);

          const rawProvider = it.provider || matchedWorker?.provider;
          let resolvedProvider = rawProvider;
          if (!resolvedProvider || resolvedProvider === "default") {
            const mLower = (it.executed_model || executedModel || "").toLowerCase();
            if (mLower.includes("gemini") || mLower.includes("gemma")) resolvedProvider = "gemini";
            else if (mLower.includes("groq") || mLower.includes("llama") || mLower.includes("mixtral") || mLower.includes("qwen") || mLower.includes("allam")) resolvedProvider = "groq";
            else if (mLower.includes("cerebras")) resolvedProvider = "cerebras";
            else if (mLower.includes("claude") || mLower.includes("anthropic")) resolvedProvider = "anthropic";
            else if (mLower.includes("openai") || mLower.includes("gpt")) resolvedProvider = "openai";
            else resolvedProvider = rawProvider || "groq";
          }

          return {
            id: it.request_id,
            timestamp: new Date(it.created_at || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            status: it.status === "success" ? "completed" : "failed",
            requestedModel: it.requested_model || it.model || "auto",
            executedModel: it.executed_model || executedModel,
            executionMode: it.execution_mode || "SINGLE",
            routingPolicy: it.routing_policy || dec?.policy || "balanced",
            provider: resolvedProvider,
            worker: matchedWorker?.name || it.worker_id || "groq/compound-mini",
            latencyMs: it.total_latency_ms || Math.round(it.latency_ms || 0),
            ttftMs: it.ttft_ms || 0,
            tokens: {
              input: inTok,
              output: outTok,
              total: totTok,
            },
            cost: it.cost !== undefined ? it.cost : 0.0,
            commercialCost: it.commercial_cost !== undefined ? it.commercial_cost : ((inTok * 0.0000025) + (outTok * 0.0000100)),
            savedCost: it.saved_cost !== undefined ? it.saved_cost : ((inTok * 0.0000025) + (outTok * 0.0000100)),
            isFreeTier: it.is_free_tier !== undefined ? it.is_free_tier : true,
            retries: it.retries || 0,
            nodes: it.execution_mode === "DAG" ? (it.subtasks_count || 4) : 1,
            parallelNodes: it.execution_mode === "DAG" ? (it.parallelism_factor || 2) : 1,
            criticalPathSeconds: (it.critical_path_ms ? it.critical_path_ms / 1000 : (it.total_latency_ms ? it.total_latency_ms / 1000 : 0)),
            totalExecutionSeconds: (it.total_latency_ms ? it.total_latency_ms / 1000 : 0),
            workstreams: it.execution_mode === "DAG" ? ["api", "db", "analytics", "frontend"] : undefined,
            clientPromptSnippet: it.decision_reason || dec?.decision_reason || "Direct execution via configured model.",
            decisionReason: it.decision_reason || dec?.decision_reason,
            candidateWorkers: it.candidate_workers || dec?.candidate_workers || [],
            streamed: it.streamed || false,
          };
        });
        setRequests(mapped);
      }
    } catch (e) {
      console.error("Requests fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRequests();
    const interval = setInterval(fetchRequests, 12000);
    return () => clearInterval(interval);
  }, [fetchRequests]);

  const filteredRequests = useMemo(() => {
    return requests.filter((r) => {
      if (modeFilter !== "ALL" && r.executionMode !== modeFilter) return false;
      if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          r.id.toLowerCase().includes(q) ||
          r.requestedModel.toLowerCase().includes(q) ||
          r.executedModel.toLowerCase().includes(q) ||
          r.provider.toLowerCase().includes(q) ||
          r.worker.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [requests, modeFilter, statusFilter, searchQuery]);

  const stats = useMemo(() => {
    const total = requests.length;
    const completed = requests.filter((r) => r.status === "completed").length;
    const successRate = total > 0 ? ((completed / total) * 100).toFixed(1) : "100";
    const avgLatency = total > 0 ? Math.round(requests.reduce((acc, r) => acc + r.latencyMs, 0) / total) : 0;
    const totalSaved = requests.reduce((acc, r) => acc + (r.savedCost || r.commercialCost || 0), 0);
    return { total, successRate, avgLatency, totalSaved };
  }, [requests]);

  return (
    <div className="page-container">
      {/* Page Title Bar */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Layers size={18} style={{ color: "var(--accent)" }} />
            <span>Requests Telemetry</span>
          </h1>
          <p className="page-subtitle">
            Observable request routing, requested vs executed models, and execution traces
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <button className="btn btn-secondary btn-sm" onClick={fetchRequests} disabled={loading} title="Refresh telemetry">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Top Telemetry Summary Strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem" }}>
        <div className="operational-card">
          <div className="op-card-header">
            <span>TOTAL TELEMETRY</span>
            <span className="op-card-trend neutral font-mono">{requests.length} logged</span>
          </div>
          <div className="op-card-main">
            <span className="op-card-val">{stats.total}</span>
            <span className="text-secondary font-mono text-xs">requests</span>
          </div>
          <div className="op-card-footer">
            <span>Mode: <strong className="font-mono text-primary">{modeFilter}</strong></span>
            <span>Status: <strong className="font-mono text-secondary">{statusFilter.toUpperCase()}</strong></span>
          </div>
        </div>

        <div className="operational-card">
          <div className="op-card-header">
            <span>SUCCESS RELIABILITY</span>
            <span className="op-card-trend up font-mono">{stats.successRate}%</span>
          </div>
          <div className="op-card-main">
            <span className="op-card-val font-mono" style={{ color: "var(--success)" }}>{stats.successRate}%</span>
            <span className="text-secondary font-mono text-xs">
              {requests.filter(r => r.status === "failed").length === 0 ? "zero-error" : "production"}
            </span>
          </div>
          <div className="op-card-footer">
            <span>Completed: <strong className="font-mono text-primary">{requests.filter(r => r.status === "completed").length}</strong></span>
            <span>Failed: <strong className="font-mono text-secondary">{requests.filter(r => r.status === "failed").length}</strong></span>
          </div>
        </div>

        <div className="operational-card">
          <div className="op-card-header">
            <span>MEAN LATENCY</span>
            <span className="op-card-trend neutral font-mono">p50</span>
          </div>
          <div className="op-card-main">
            <span className="op-card-val font-mono">{stats.avgLatency}ms</span>
            <span className="text-secondary font-mono text-xs">wall-clock</span>
          </div>
          <div className="op-card-footer">
            <span>Speed: <strong className="font-mono text-primary">{stats.avgLatency < 1000 ? "Sub-second" : "Standard"}</strong></span>
            <span>Live Trace Active</span>
          </div>
        </div>

        <div className="operational-card">
          <div className="op-card-header">
            <span>VALUE ACCELERATION</span>
            <span className="op-card-trend up font-mono" style={{ color: "var(--success)" }}>+100% saved</span>
          </div>
          <div className="op-card-main">
            <span className="op-card-val font-mono" style={{ color: "var(--success)" }}>+${stats.totalSaved.toFixed(3)}</span>
            <span className="text-secondary font-mono text-xs">benchmark</span>
          </div>
          <div className="op-card-footer">
            <span>Spend: <strong className="font-mono text-primary">$0.0000</strong></span>
            <span style={{ color: "var(--text-tertiary)" }}>Free Tier Virtualizer</span>
          </div>
        </div>
      </div>

      {/* Table Filter and Search Bar */}
      <div className="table-toolbar">
        <div className="search-input-wrap">
          <Search size={14} />
          <input
            type="text"
            className="search-input"
            placeholder="Search request ID, model, provider... (Press / to search)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          {/* Results Count Chip */}
          <span style={{ fontSize: "0.6875rem", fontFamily: "var(--font-mono)", color: "var(--text-tertiary)", backgroundColor: "var(--bg-elevated)", padding: "0.2rem 0.5rem", borderRadius: "var(--radius-xs)", border: "1px solid var(--border-subtle)" }}>
            Showing {filteredRequests.length} of {requests.length}
          </span>

          {/* Mode Filter */}
          <div className="filter-btn-group">
            <span style={{ fontSize: "0.6875rem", padding: "0.2rem 0.45rem", color: "var(--text-tertiary)", fontWeight: 600 }}>MODE:</span>
            {(["ALL", "DAG", "SINGLE"] as const).map((m) => (
              <button
                key={m}
                className={`filter-btn ${modeFilter === m ? "active" : ""}`}
                onClick={() => setModeFilter(m)}
              >
                {m}
              </button>
            ))}
          </div>

          {/* Status Filter */}
          <div className="filter-btn-group">
            <span style={{ fontSize: "0.6875rem", padding: "0.2rem 0.45rem", color: "var(--text-tertiary)", fontWeight: 600 }}>STATUS:</span>
            {(["ALL", "completed", "failed"] as const).map((s) => (
              <button
                key={s}
                className={`filter-btn ${statusFilter === s ? "active" : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Dense Requests Table */}
      <div className="dense-table-wrapper">
        <table className="dense-table dense-table-wide">
          <thead>
            <tr>
              <th>Time</th>
              <th style={{ width: "125px" }}>Request ID</th>
              <th>Requested Model</th>
              <th>Executed Model</th>
              <th>Provider</th>
              <th>Execution</th>
              <th>Route Policy</th>
              <th>Latency</th>
              <th>Tokens</th>
              <th>Cost</th>
              <th style={{ textAlign: "center", width: "50px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && requests.length === 0 ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`skel-req-${i}`}>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "65px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "105px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "120px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "120px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-pill" style={{ width: "68px", height: "18px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "50px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "65px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "45px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "45px" }} /></td>
                  <td><span className="skeleton-shimmer skeleton-line" style={{ width: "60px" }} /></td>
                  <td style={{ textAlign: "center" }}>
                    <span className="skeleton-shimmer skeleton-pill" style={{ width: "8px", height: "8px", borderRadius: "50%" }} />
                  </td>
                </tr>
              ))
            ) : (
              filteredRequests.map((req) => {
                const isGemini = (req.executedModel || "").toLowerCase().includes("gemini");
                const isGroq = (req.provider || "").toLowerCase().includes("groq") || (req.executedModel || "").toLowerCase().includes("qwen");

                return (
                  <tr
                    key={req.id}
                    className={`fade-in ${selectedRequest?.id === req.id ? "selected" : ""}`}
                    onClick={() => setSelectedRequest(req)}
                  >
                    <td className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>{req.timestamp}</td>
                    <td
                      className="font-mono text-primary"
                      style={{
                        fontWeight: 600,
                        fontSize: "0.6875rem",
                        maxWidth: "125px",
                        whiteSpace: "nowrap",
                      }}
                      title={`Request ID: ${req.id} (Click row for details)`}
                    >
                      {formatShortRequestId(req.id)}
                    </td>
                    <td>
                      <span className="model-cell-requested" title={req.requestedModel}>{req.requestedModel}</span>
                    </td>
                    <td>
                      {(() => {
                        const execBadge = formatExecutedModelBadge(req.executedModel, req.executionMode);
                        if (execBadge.isMulti) {
                          return (
                            <span
                              className="model-cell-executed model-cell-dag-multi"
                              title={execBadge.fullTitle}
                            >
                              <Layers size={11} style={{ flexShrink: 0, opacity: 0.85 }} />
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {execBadge.label}
                              </span>
                            </span>
                          );
                        }
                        return (
                          <span
                            className="model-cell-executed"
                            title={req.executedModel}
                            style={{
                              borderColor: isGemini ? "rgba(99, 102, 241, 0.35)" : (isGroq ? "rgba(249, 115, 22, 0.35)" : "var(--border-strong)"),
                              backgroundColor: isGemini ? "rgba(99, 102, 241, 0.08)" : (isGroq ? "rgba(249, 115, 22, 0.08)" : "var(--bg-elevated)"),
                              color: isGemini ? "#818cf8" : (isGroq ? "#fb923c" : "var(--text-primary)"),
                            }}
                          >
                            {req.executedModel}
                          </span>
                        );
                      })()}
                    </td>
                    <td>
                      {(() => {
                        const provInfo = parseProviderInfo(req.provider, req.executedModel);
                        return (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              color: provInfo.badgeStyle.color,
                              backgroundColor: provInfo.badgeStyle.bg,
                              border: `1px solid ${provInfo.badgeStyle.border}`,
                              borderRadius: "var(--radius-xs)",
                              padding: "0.12rem 0.45rem",
                              letterSpacing: "0.02em",
                              maxWidth: "140px",
                              whiteSpace: "nowrap",
                              cursor: provInfo.isMulti ? "pointer" : "default",
                            }}
                            title={provInfo.tooltip}
                          >
                            <span style={{ display: "inline-flex", gap: "2px", alignItems: "center", flexShrink: 0 }}>
                              {provInfo.providers.map((pr, idx) => (
                                <span
                                  key={idx}
                                  style={{
                                    width: "5px",
                                    height: "5px",
                                    borderRadius: "50%",
                                    backgroundColor: pr.dot,
                                    display: "inline-block",
                                    boxShadow: `0 0 4px ${pr.dot}66`,
                                  }}
                                />
                              ))}
                            </span>
                            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {provInfo.label}
                            </span>
                          </span>
                        );
                      })()}
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          fontFamily: "var(--font-mono)",
                          padding: "0.1rem 0.4rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor: req.executionMode === "DAG" ? "var(--accent-muted)" : "var(--bg-elevated)",
                          color: req.executionMode === "DAG" ? "var(--accent)" : "var(--text-secondary)",
                          border: req.executionMode === "DAG" ? "1px solid var(--accent-border)" : "1px solid var(--border-subtle)",
                          fontWeight: req.executionMode === "DAG" ? 600 : 500,
                        }}
                      >
                        {req.executionMode}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.6875rem", color: "var(--text-secondary)" }}>
                      <span style={{ padding: "0.1rem 0.35rem", borderRadius: "var(--radius-xs)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)" }}>
                        {req.routingPolicy}
                      </span>
                    </td>
                    <td className="font-mono text-primary" style={{ fontWeight: 600 }}>
                      <span style={{ color: req.latencyMs < 1000 ? "var(--success)" : (req.latencyMs < 5000 ? "var(--text-primary)" : "var(--warning)") }}>
                        {req.latencyMs}ms
                      </span>
                    </td>
                    <td className="font-mono text-secondary">{req.tokens.total.toLocaleString()}</td>
                    <td className="font-mono" style={{ whiteSpace: "nowrap" }}>
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>${(req.cost || 0).toFixed(4)}</span>
                      {req.isFreeTier !== false && (
                        <span
                          style={{
                            display: "block",
                            fontSize: "0.625rem",
                            color: "var(--text-tertiary)",
                            lineHeight: 1.1,
                            marginTop: "0.1rem",
                          }}
                          title={`Commercial equivalent: +$${(req.savedCost || req.commercialCost || 0).toFixed(4)} saved`}
                        >
                          (+${(req.savedCost || req.commercialCost || 0).toFixed(3)})
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <span
                        className={`status-dot ${req.status === "completed" ? "healthy" : "failed"}`}
                        title={req.status}
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {!loading && filteredRequests.length === 0 && (
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>
            <Filter size={20} style={{ margin: "0 auto 0.5rem", opacity: 0.5 }} />
            <span>No requests matching filter criteria</span>
          </div>
        )}
      </div>

      {/* Inspectable Request Slide-Over Drawer */}
      <RequestDrawer request={selectedRequest} onClose={() => setSelectedRequest(null)} />
    </div>
  );
}
