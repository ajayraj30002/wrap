import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Activity, ArrowUpRight, LayoutDashboard, Zap, ShieldCheck, Layers, DollarSign } from "lucide-react";
import { DAGTopology } from "../components/ui/DAGTopology";

import { RequestDrawer, type RequestDetailData } from "../components/ui/RequestDrawer";
import { apiClient } from "../lib/apiClient";
import { formatShortRequestId, formatExecutedModelBadge, parseProviderInfo } from "../lib/providerBadges";

export interface CacheStats {
  entries_count: number;
  max_entries: number;
  total_hits: number;
  total_misses: number;
  hit_rate_pct: number;
  total_tokens_saved: number;
}

interface CachedOverviewState {
  systemState: {
    traffic: { count: string; change: string; p50: string; p95: string };
    routing: { autoPct: string; change: string; routedChanges: number; fallbacks: number };
    economics: { actualSpend: string; commercialSaved: string; freePct: string };
    resources: { capacityPct: string; change: string; activeWorkers: number; degraded: number };
  } | null;
  requestsList: RequestDetailData[];
  workersList: any[];
  dag: any;
}

function getInitialOverview(): CachedOverviewState | null {
  try {
    const raw = sessionStorage.getItem("wrap_cached_overview");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

let cachedOverview: CachedOverviewState | null = getInitialOverview();

export function Overview() {
  const [loading, setLoading] = useState(!cachedOverview);
  const [timeRange, setTimeRange] = useState<"1h" | "24h" | "7d">("7d");
  const [selectedRequest, setSelectedRequest] = useState<RequestDetailData | null>(null);
  const [requestsList, setRequestsList] = useState<RequestDetailData[]>(cachedOverview?.requestsList || []);
  const [workersList, setWorkersList] = useState<any[]>(cachedOverview?.workersList || []);
  const [initialDag, setInitialDag] = useState<any | null>(cachedOverview?.dag || null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [agentResilience, setAgentResilience] = useState<any>(null);
  const [sseConnected, setSseConnected] = useState<boolean>(false);

  // Operational metrics state (cached initially to prevent flash on tab change)
  const [systemState, setSystemState] = useState<{
    traffic: { count: string; change: string; p50: string; p95: string };
    routing: { autoPct: string; change: string; routedChanges: number; fallbacks: number };
    economics: { actualSpend: string; commercialSaved: string; freePct: string };
    resources: { capacityPct: string; change: string; activeWorkers: number; degraded: number };
  } | null>(cachedOverview?.systemState || null);

  const fetchOverviewData = useCallback(async (selectedRange?: "1h" | "24h" | "7d", isManualRefresh = false) => {
    const rangeToFetch = selectedRange || timeRange;
    if (!cachedOverview || isManualRefresh) {
      setLoading(true);
    }
    try {
      const data = await apiClient.get(`/api/dashboard/overview?range=${rangeToFetch}`, {
        bypassCache: isManualRefresh,
      });
      if (!data) return;

      if (data.agent_resilience) {
        setAgentResilience(data.agent_resilience);
      }

      // 1. Process Workers

      const currentWorkers: any[] = Array.isArray(data.workers) ? data.workers : [];
      setWorkersList(currentWorkers);

      // 2. Set initial DAG run
      if (data.dag) {
        setInitialDag(data.dag);
      }

      // 3. Process Requests
      const rawRequests = Array.isArray(data.requests) ? data.requests : [];
      let mappedRequests: RequestDetailData[] = [];
      if (rawRequests.length > 0) {
        mappedRequests = rawRequests.map((it: any) => {
          const matchedWorker = currentWorkers.find((w) => w.id === it.worker_id);

          const inTok = it.input_tokens || 0;
          const outTok = it.output_tokens || 0;
          const totTok = it.total_tokens || (inTok + outTok);

          return {
            id: it.request_id,
            timestamp: new Date(it.created_at || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            status: it.status === "success" ? "completed" : "failed",
            requestedModel: it.requested_model || it.model || "auto",
            executedModel: it.executed_model || matchedWorker?.model || (it.model === "auto" ? "groq/compound-mini" : it.model),
            executionMode: it.execution_mode || "SINGLE",
            routingPolicy: it.routing_policy || "balanced",
            provider: it.provider || matchedWorker?.provider || "groq",
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
            clientPromptSnippet: it.decision_reason || "Direct execution via configured model.",
            decisionReason: it.decision_reason,
            candidateWorkers: it.candidate_workers || [],
            streamed: it.streamed || false,
          };
        });
      }
      setRequestsList(mappedRequests);

      // 4. Process Overview Metrics
      let nextSystemState = null;
      if (data.overview) {
        const ov = data.overview;
        const total = ov.total_requests || 0;
        const avgSec = ov.average_latency_ms ? `${(ov.average_latency_ms / 1000).toFixed(1)}s` : "0.0s";
        const p95Sec = ov.p95_latency_ms ? `${(ov.p95_latency_ms / 1000).toFixed(1)}s` : "0.0s";
        const autoPct = ov.auto_routed_percentage != null ? `${ov.auto_routed_percentage}%` : "100%";
        const activeWorkers = ov.active_workers || currentWorkers.length || 0;
        const degraded = ov.unhealthy_workers || 0;
        const headroomPct = activeWorkers > 0 ? "100%" : "0%";

        nextSystemState = {
          traffic: {
            count: String(total),
            change: total > 0 ? "Live" : "Idle",
            p50: avgSec,
            p95: p95Sec,
          },
          routing: {
            autoPct,
            change: "Active",
            routedChanges: total,
            fallbacks: degraded,
          },
          economics: {
            actualSpend: `$${(ov.actual_cost_usd || 0).toFixed(4)}`,
            commercialSaved: `$${(ov.total_saved_usd || ov.commercial_equivalent_usd || 0).toFixed(3)}`,
            freePct: `${ov.savings_percentage != null ? ov.savings_percentage : 100}% Saved`,
          },
          resources: {
            capacityPct: headroomPct,
            change: degraded > 0 ? "Degraded" : "Optimal",
            activeWorkers,
            degraded,
          },
        };
        setSystemState(nextSystemState);
      }

      // Save to memory cache for instantaneous tab returns
      cachedOverview = {
        systemState: nextSystemState || cachedOverview?.systemState || null,
        requestsList: mappedRequests,
        workersList: currentWorkers.length > 0 ? currentWorkers : (cachedOverview?.workersList || []),
        dag: data.dag || cachedOverview?.dag || null,
      };
      try {
        sessionStorage.setItem("wrap_cached_overview", JSON.stringify(cachedOverview));
      } catch {}
    } catch (e) {
      console.error("Failed to load overview data:", e);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchOverviewData();

    // 1. Establish real-time SSE stream with automatic reconnection
    let es: EventSource | null = null;
    let fallbackInterval: ReturnType<typeof setInterval> | null = null;

    try {
      es = new EventSource("/api/stream/telemetry");
      es.onopen = () => {
        setSseConnected(true);
      };
      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.cache) {
            setCacheStats(payload.cache);
          }
          if (payload.topbar) {
            setSystemState((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                traffic: {
                  ...prev.traffic,
                  count: String(payload.topbar.total_requests ?? prev.traffic.count),
                  change: payload.topbar.total_requests > 0 ? "Live" : prev.traffic.change,
                },
                resources: {
                  ...prev.resources,
                  activeWorkers: payload.topbar.workers_count ?? prev.resources.activeWorkers,
                },
              };
            });
          }
        } catch (err) {
          console.error("Error parsing telemetry stream event:", err);
        }
      };
      es.onerror = () => {
        setSseConnected(false);
      };
    } catch {
      setSseConnected(false);
    }

    // 2. High-level dashboard periodic refresh fallback (requests table + DAG)
    fallbackInterval = setInterval(() => fetchOverviewData(timeRange), 10000);

    return () => {
      if (es) es.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
    };
  }, [fetchOverviewData, timeRange]);

  const activeRequestId = selectedRequest?.id || undefined;

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <LayoutDashboard size={18} style={{ color: "var(--accent)" }} />
            <span>System Overview</span>
          </h1>
          <p className="page-subtitle">
            Real-time model routing, live execution topology, and token economic performance
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {/* SSE Live Telemetry Indicator */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.25rem 0.65rem",
              borderRadius: "9999px",
              fontSize: "0.6875rem",
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              letterSpacing: "0.04em",
              background: sseConnected ? "var(--success-muted)" : "var(--bg-elevated)",
              border: `1px solid ${sseConnected ? "var(--success-border)" : "var(--border-subtle)"}`,
              color: sseConnected ? "var(--success)" : "var(--text-tertiary)",
            }}
            title={sseConnected ? "Real-time SSE telemetry active (2s heartbeat)" : "Falling back to 10s polling"}
          >
            <span
              style={{
                position: "relative",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: sseConnected ? "var(--success)" : "var(--text-tertiary)",
                boxShadow: sseConnected ? "0 0 6px var(--success)" : "none",
              }}
            />
            <span>{sseConnected ? "SSE: LIVE" : "POLLING"}</span>
          </div>

          {/* Time Range Selector */}
          <div className="time-range-group">
            {(["1h", "24h", "7d"] as const).map((r) => (
              <button
                key={r}
                className={`time-range-btn ${timeRange === r ? "active" : ""}`}
                onClick={() => {
                  setTimeRange(r);
                  fetchOverviewData(r);
                }}
              >
                {r}
              </button>
            ))}
          </div>

          {/* Refresh Action */}
          <button className="btn btn-secondary btn-sm" onClick={() => fetchOverviewData(timeRange, true)} disabled={loading} title="Refresh metrics">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* 2. Executive Telemetry Dock (Panoramic Unified HUD) */}
      <div className="telemetry-dock">
        {!systemState ? (
          Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="telemetry-dock-cell">
              <div className="dock-cell-top">
                <span className="skeleton-shimmer skeleton-line" style={{ width: "65px", height: "12px" }} />
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "36px", height: "14px" }} />
              </div>
              <div className="dock-cell-main">
                <span className="skeleton-shimmer skeleton-metric-block" style={{ width: "55px", height: "24px" }} />
              </div>
              <div className="dock-cell-sub">
                <span className="skeleton-shimmer skeleton-line" style={{ width: "95px", height: "10px" }} />
              </div>
            </div>
          ))
        ) : (
          <>
            {/* 1. Traffic */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <Activity size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                  <span>TRAFFIC</span>
                </div>
                <span className="dock-badge up">
                  <ArrowUpRight size={10} /> {systemState.traffic.change}
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val">{systemState.traffic.count}</span>
                <span className="dock-unit">requests</span>
              </div>
              <div className="dock-cell-sub">
                p50: <strong>{systemState.traffic.p50}</strong> &bull; p95: <strong>{systemState.traffic.p95}</strong>
              </div>
            </div>

            {/* 2. Routing */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <Zap size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                  <span>ROUTING</span>
                </div>
                <span className="dock-badge up">
                  <ArrowUpRight size={10} /> {systemState.routing.change}
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val">{systemState.routing.autoPct}</span>
                <span className="dock-unit">auto-routed</span>
              </div>
              <div className="dock-cell-sub">
                <strong>{systemState.routing.routedChanges}</strong> routed &bull; <strong>{systemState.routing.fallbacks}</strong> fallbacks
              </div>
            </div>

            {/* 3. Resources */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <Activity size={13} style={{ color: "var(--success)", flexShrink: 0 }} />
                  <span>RESOURCES</span>
                </div>
                <span className={`dock-badge ${systemState.resources.degraded > 0 ? "warning" : "up"}`}>
                  <ArrowUpRight size={10} /> {systemState.resources.change}
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val">{systemState.resources.capacityPct}</span>
                <span className="dock-unit">headroom</span>
              </div>
              <div className="dock-cell-sub" title={`${systemState.resources.activeWorkers} active workers, ${systemState.resources.degraded} degraded`}>
                <strong>{systemState.resources.activeWorkers}</strong> active &bull;{" "}
                <span style={{ color: systemState.resources.degraded > 0 ? "var(--warning)" : "inherit" }}>
                  <strong>{systemState.resources.degraded}</strong> degraded
                </span>
              </div>
            </div>

            {/* 4. Cost Economics */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <DollarSign size={13} style={{ color: "var(--success)", flexShrink: 0 }} />
                  <span>ECONOMICS</span>
                </div>
                <span className="dock-badge up">
                  <ArrowUpRight size={10} /> {systemState.economics.freePct}
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val" style={{ color: "var(--success)" }}>
                  +{systemState.economics.commercialSaved}
                </span>
                <span className="dock-unit" style={{ color: "var(--success)" }}>saved</span>
              </div>
              <div className="dock-cell-sub">
                spend <strong>{systemState.economics.actualSpend}</strong> &bull; {timeRange} window
              </div>
            </div>

            {/* 5. Edge Response Cache */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <Zap size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                  <span>EDGE CACHE</span>
                </div>
                <span className="dock-badge accent">
                  {cacheStats && cacheStats.hit_rate_pct > 0 ? `${cacheStats.hit_rate_pct}% Hits` : "0ms Fast"}
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val" style={{ color: "var(--accent)" }}>
                  {cacheStats ? cacheStats.total_tokens_saved.toLocaleString() : "0"}
                </span>
                <span className="dock-unit">tokens saved</span>
              </div>
              <div className="dock-cell-sub" title={`Capacity: ${cacheStats ? `${cacheStats.entries_count}/${cacheStats.max_entries}` : "0/5000"} LRU entries`}>
                <strong>{cacheStats?.total_hits ?? 0}</strong> hits &bull; <strong>{cacheStats?.total_misses ?? 0}</strong> misses
              </div>
            </div>

            {/* 6. Agent Resilience */}
            <div className="telemetry-dock-cell fade-in">
              <div className="dock-cell-top">
                <div className="dock-title-group">
                  <ShieldCheck size={13} style={{ color: "var(--success)", flexShrink: 0 }} />
                  <span>AGENT SHIELD</span>
                </div>
                <span className="dock-badge up">
                  Zero-Error
                </span>
              </div>
              <div className="dock-cell-main">
                <span className="dock-hero-val" style={{ color: "var(--success)" }}>
                  {agentResilience ? agentResilience.healed_tool_calls_count : 0}
                </span>
                <span className="dock-unit">calls healed</span>
              </div>
              <div className="dock-cell-sub" title="Model Tier: Frontier ↔ Speed | Compactor: Active">
                Frontier ↔ Speed
              </div>
            </div>
          </>
        )}
      </div>

      {/* 3. Live Contextual Execution Topology */}
      <DAGTopology
        selectedRequestId={activeRequestId}
        initialDagData={initialDag}
        realWorkers={workersList}
        onNodeSelect={() => {
          if (requestsList.length > 0 && !selectedRequest) setSelectedRequest(requestsList[0]);
        }}
      />

      {/* 4. Requests Stream from Database */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Activity size={14} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Request Logs & Routing Decisions
            </span>
          </div>
          <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
            Click any row to inspect routing score breakdown & candidate evaluation
          </span>
        </div>

        <div className="dense-table-wrapper">
          <table className="dense-table dense-table-wide">
            <thead>
              <tr>
                <th>Time</th>
                <th style={{ width: "125px" }}>Request ID</th>
                <th>Requested Model</th>
                <th>Executed Model</th>
                <th>Provider</th>
                <th>Route Policy</th>
                <th>Latency</th>
                <th>Tokens</th>
                <th>Billed Cost</th>
                <th>Value Saved</th>
                <th style={{ textAlign: "center", width: "70px" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading && requestsList.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={`skel-req-${i}`}>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "65px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "105px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "115px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "115px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "50px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "65px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "45px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "40px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "55px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "55px" }} /></td>
                    <td style={{ textAlign: "center" }}>
                      <span className="skeleton-shimmer skeleton-pill" style={{ width: "8px", height: "8px", borderRadius: "50%" }} />
                    </td>
                  </tr>
                ))
              ) : requestsList.length === 0 ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: "center", padding: "2.5rem", color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>
                    No requests recorded yet. Send your first API request through the gateway to populate live telemetry.
                  </td>
                </tr>
              ) : (
                requestsList.map((req) => {
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
                      <td className="font-mono" style={{ color: "var(--success)", fontWeight: 600 }}>${(req.cost || 0).toFixed(4)}</td>
                      <td className="font-mono" style={{ color: "var(--text-secondary)" }}>+${(req.savedCost || req.commercialCost || 0).toFixed(4)}</td>
                      <td style={{ textAlign: "center" }}>
                        <span className={`status-dot ${req.status === "failed" ? "degraded" : "healthy"}`} />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Inspectable Request Slide-Over Drawer */}
      <RequestDrawer request={selectedRequest} onClose={() => setSelectedRequest(null)} />
    </div>
  );
}
