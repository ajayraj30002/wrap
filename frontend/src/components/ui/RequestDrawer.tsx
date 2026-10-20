import { useState, useEffect } from "react";
import { X, Copy, Check, RotateCcw, CheckCircle2, XCircle, Cpu, Layers } from "lucide-react";
import { RoutingDecisionTrace } from "./RoutingDecisionTrace";
import { ExecutionTrace } from "./ExecutionTrace";
import { apiClient } from "../../lib/apiClient";
import { getProviderBadgeStyle, formatExecutedModelBadge, formatShortRequestId } from "../../lib/providerBadges";

export interface RequestDetailData {
  id: string;
  timestamp: string;
  status: "completed" | "running" | "failed";
  requestedModel: string;
  executedModel: string;
  executionMode: "SINGLE" | "DAG";
  routingPolicy: string;
  provider: string;
  worker: string;
  latencyMs: number;
  ttftMs: number;
  tokens: {
    input: number;
    output: number;
    total: number;
  };
  cost: number;
  commercialCost?: number;
  savedCost?: number;
  isFreeTier?: boolean;
  retries: number;
  clientPromptSnippet?: string;
  decisionReason?: string;
  candidateWorkers?: string[];
  streamed?: boolean;
  workstreams?: string[];
  nodes?: number;
  parallelNodes?: number;
  criticalPathSeconds?: number;
  totalExecutionSeconds?: number;
}

interface RequestDrawerProps {
  request: RequestDetailData | null;
  onClose: () => void;
}

export function RequestDrawer({ request, onClose }: RequestDrawerProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "routing" | "execution" | "timeline" | "replay" | "tokens" | "raw">("overview");
  const [copied, setCopied] = useState(false);
  const [realMetrics, setRealMetrics] = useState<any | null>(null);
  const [realTimeline, setRealTimeline] = useState<any | null>(null);
  const [replayData, setReplayData] = useState<any | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);

  const isDag = request?.executionMode === "DAG";
  const availableTabs = isDag
    ? (["overview", "routing", "execution", "timeline", "replay", "tokens", "raw"] as const)
    : (["overview", "routing", "tokens", "raw"] as const);

  useEffect(() => {
    if (!availableTabs.includes(activeTab as any)) {
      setActiveTab("overview");
    }
  }, [availableTabs, activeTab]);

  useEffect(() => {
    if (!request?.id) return;
    if (!isDag) {
      setRealMetrics(null);
      setRealTimeline(null);
      return;
    }
    let isMounted = true;
    Promise.allSettled([
      apiClient.get(`/workflows/${request.id}/metrics`),
      apiClient.get(`/workflows/${request.id}/timeline`),
    ]).then(([mRes, tRes]) => {
      if (!isMounted) return;
      if (mRes.status === "fulfilled" && mRes.value) {
        setRealMetrics(mRes.value);
      }
      if (tRes.status === "fulfilled" && tRes.value) {
        setRealTimeline(tRes.value);
      }
    });
    return () => {
      isMounted = false;
    };
  }, [request?.id, isDag]);

  const handleFetchReplay = async () => {
    if (!request?.id || !isDag) return;
    setReplayLoading(true);
    try {
      const res = await apiClient.get(`/workflows/${request.id}/replay`);
      setReplayData(res);
    } catch (e) {
      console.error("Replay fetch failed:", e);
    } finally {
      setReplayLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "replay" && !replayData && !replayLoading && isDag) {
      handleFetchReplay();
    }
  }, [activeTab, request?.id, isDag]);

  if (!request) return null;

  const handleCopyRaw = () => {
    navigator.clipboard.writeText(
      JSON.stringify({ ...request, liveMetrics: realMetrics, eventTimeline: realTimeline, replay: replayData }, null, 2)
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const requestedModel = realTimeline?.requested_model || request.requestedModel || "auto";
  const executedModel = realTimeline?.executed_model || request.executedModel || "auto";
  const execBadge = formatExecutedModelBadge(executedModel, request.executionMode);
  // Parse distinct providers
  const rawProviders = (request.provider || "")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  const providersList = rawProviders.length > 0 ? Array.from(new Set(rawProviders)) : ["groq"];


  // Build structured provider groups for "Participating Providers & Executed Models"
  interface SubtaskItem {
    taskId?: string;
    model: string;
    description?: string;
  }
  interface ProviderGroup {
    provider: string;
    items: SubtaskItem[];
  }

  // Extract from realTimeline.events if present
  const taskEvents = (realTimeline?.events || []).filter(
    (e: any) => e.event_type === "TASK_STARTED" && (e.payload?.model || e.task_id)
  );

  let providerGroups: ProviderGroup[] = [];

  if (taskEvents.length > 0) {
    const map = new Map<string, SubtaskItem[]>();
    for (const ev of taskEvents) {
      const p = ev.payload?.provider || "groq";
      const item: SubtaskItem = {
        taskId: ev.task_id,
        model: ev.payload?.model || "default",
        description: ev.payload?.description || "",
      };
      if (!map.has(p)) map.set(p, []);
      map.get(p)!.push(item);
    }
    providerGroups = Array.from(map.entries()).map(([provider, items]) => ({ provider, items }));
  } else {
    // Fallback: group the executed models by their provider
    const modelsList = execBadge.models.length > 0 ? execBadge.models : [executedModel];
    const map = new Map<string, SubtaskItem[]>();
    for (const m of modelsList) {
      const style = getProviderBadgeStyle(undefined, m);
      const provName = style.name;
      if (!map.has(provName)) map.set(provName, []);
      map.get(provName)!.push({
        model: m,
      });
    }
    providerGroups = Array.from(map.entries()).map(([provider, items]) => ({ provider, items }));
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="request-drawer">
        {/* Header */}
        <div className="drawer-header">
          <div className="drawer-title-group" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span className="drawer-request-id" title={request.id}>{formatShortRequestId(request.id)}</span>
            <span className={`status-pill ${request.status === "failed" ? "error" : ""}`}>
              <span className="status-pulse" />
              {request.status.toUpperCase()}
            </span>
            <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
              {request.timestamp}
            </span>
          </div>
          <button className="btn btn-ghost" onClick={onClose} title="Close drawer">
            <X size={16} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="drawer-tabs">
          {availableTabs.map((tab) => (
            <button
              key={tab}
              className={`drawer-tab-btn ${activeTab === tab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Tab Body */}
        <div className="drawer-body">
          {activeTab === "overview" && (
            <>
              {/* Requested vs Executed Comparison Banner */}
              <div className="drawer-section">
                <div className="drawer-section-title">Model Resolution</div>
                <div className="info-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <div className="info-row">
                    <span className="info-label">REQUESTED MODEL</span>
                    <span className="model-cell-requested" style={{ fontWeight: 600, maxWidth: "100%", width: "fit-content" }}>
                      {requestedModel}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">ACTUALLY EXECUTED</span>
                    {execBadge.isMulti ? (
                      <span
                        className="model-cell-executed model-cell-dag-multi"
                        style={{
                          fontWeight: 600,
                          maxWidth: "100%",
                          width: "fit-content",
                          padding: "0.2rem 0.55rem",
                        }}
                        title={execBadge.fullTitle}
                      >
                        <Cpu size={12} />
                        <span>DAG Mesh ({execBadge.count} Models)</span>
                      </span>
                    ) : (
                      <span
                        className="model-cell-executed"
                        style={{ fontWeight: 600, color: "var(--accent)", maxWidth: "100%", width: "fit-content" }}
                      >
                        {executedModel}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Routing Rationale & Context */}
              <div className="drawer-section">
                <div className="drawer-section-title">Routing Decision & Rationale</div>
                <div style={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", padding: "0.75rem", fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  {request.decisionReason || request.clientPromptSnippet || "Direct execution via configured model."}
                </div>
                {request.workstreams && request.workstreams.length > 0 && (
                  <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", marginTop: "0.4rem" }}>
                    {request.workstreams.map((ws) => (
                      <span key={ws} style={{ fontSize: "0.625rem", fontFamily: "var(--font-mono)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", padding: "0.15rem 0.4rem", borderRadius: "var(--radius-xs)", color: "var(--text-tertiary)" }}>
                        #{ws}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Participating Providers & Subtask Model Mesh */}
              <div className="drawer-section">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div className="drawer-section-title" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Layers size={13} style={{ color: "var(--accent)" }} />
                    <span>Participating Providers & Executed Models</span>
                  </div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                    {providerGroups.length} {providerGroups.length === 1 ? "Provider" : "Providers"} • {execBadge.count} {execBadge.count === 1 ? "Model" : "Models"}
                  </span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {providerGroups.map((group) => {
                    const badge = getProviderBadgeStyle(group.provider);
                    return (
                      <div
                        key={group.provider}
                        style={{
                          backgroundColor: "var(--bg-elevated)",
                          border: `1px solid ${badge.border}`,
                          borderRadius: "var(--radius-sm)",
                          padding: "0.625rem 0.75rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.45rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            <span
                              style={{
                                width: "7px",
                                height: "7px",
                                borderRadius: "50%",
                                backgroundColor: badge.dot,
                                display: "inline-block",
                              }}
                            />
                            <span style={{ fontWeight: 600, fontSize: "0.8125rem", color: badge.color }}>
                              {badge.name}
                            </span>
                          </div>
                          <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                            {group.items.length} {group.items.length === 1 ? "Subtask" : "Subtasks"}
                          </span>
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                          {group.items.map((item, idx) => (
                            <div
                              key={idx}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                padding: "0.25rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                                backgroundColor: "var(--bg-surface)",
                                fontSize: "0.72rem",
                                border: "1px solid var(--border-subtle)",
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", minWidth: 0, flexWrap: "wrap" }}>
                                {item.taskId && (
                                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", color: "var(--accent)", fontWeight: 600 }}>
                                    [{item.taskId}]
                                  </span>
                                )}
                                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                                  {item.model}
                                </span>
                                {item.description && (
                                  <span style={{ color: "var(--text-secondary)", fontSize: "0.6875rem" }}>
                                    — {item.description}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Execution Timing & Latency (For single-model execution) */}
              {request.executionMode !== "DAG" && (
                <div className="drawer-section">
                  <div className="drawer-section-title">Execution Timing & Latency</div>
                  <div className="info-grid">
                    <div className="info-row">
                      <span className="info-label">Time to First Token (TTFT)</span>
                      <span className="info-val font-mono">{request.ttftMs ?? 0}ms</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Generation Duration</span>
                      <span className="info-val font-mono">{Math.max(0, request.latencyMs - (request.ttftMs ?? 0))}ms</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Total Latency</span>
                      <span className="info-val font-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>{request.latencyMs}ms</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Stream Mode</span>
                      <span className="info-val">{request.streamed ? "Active (SSE Stream)" : "Standard Response"}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Execution Summary & Concurrency */}
              <div className="drawer-section">
                <div className="drawer-section-title">Execution Architecture & Concurrency</div>
                <div className="info-grid">
                  <div className="info-row">
                    <span className="info-label">Execution Mode</span>
                    <span className="info-val font-mono">{request.executionMode}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Routing Policy</span>
                    <span className="info-val font-mono">{request.routingPolicy}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Provider</span>
                    <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", marginTop: "0.15rem" }}>
                      {providersList.map((p) => {
                        const style = getProviderBadgeStyle(p);
                        return (
                          <span
                            key={p}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              padding: "0.12rem 0.45rem",
                              borderRadius: "9999px",
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              color: style.color,
                              backgroundColor: style.bg,
                              border: `1px solid ${style.border}`,
                            }}
                          >
                            <span style={{ width: "5px", height: "5px", borderRadius: "50%", backgroundColor: style.dot }} />
                            {style.name}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Assigned Worker</span>
                    <span className="info-val font-mono" style={{ fontSize: "0.6875rem", color: isDag ? "var(--accent)" : "inherit" }}>
                      {isDag ? `Distributed Mesh (${realMetrics?.nodes || request.parallelNodes || providerGroups.reduce((acc, g) => acc + g.items.length, 0) || 2} nodes)` : request.worker}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Parallelism Factor</span>
                    <span className="info-val font-mono" style={{ color: "var(--accent)" }}>
                      {request.executionMode === "DAG" ? `${realMetrics?.parallelism_factor || request.parallelNodes || 2}x` : "1x (Single Worker)"}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Measured Speedup Ratio</span>
                    <span className="info-val font-mono">
                      {request.executionMode === "DAG" ? (realMetrics?.observed_speedup_ratio ? `${realMetrics.observed_speedup_ratio}x` : "1.0x") : "N/A (Single Worker)"}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Total Execution Time</span>
                    <span className="info-val font-mono">
                      {request.latencyMs}ms
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Attempts & Retries</span>
                    <span className="info-val font-mono" style={{ color: (realMetrics?.total_retries ?? request.retries) > 0 ? "var(--warning)" : "var(--success)" }}>
                      {realMetrics?.total_attempts ?? (request.retries + 1)} attempts / {realMetrics?.total_retries ?? request.retries} retries ({realMetrics?.retry_overhead_ms ? `${realMetrics.retry_overhead_ms}ms overhead` : "0ms"})
                    </span>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === "routing" && (
            <div className="drawer-section">
              <div className="drawer-section-title">Transparent Decision Engine</div>
              <RoutingDecisionTrace
                policy={request.routingPolicy}
                funnel={{
                  requested: requestedModel,
                  totalCandidates: (request.candidateWorkers && request.candidateWorkers.length > 0) ? request.candidateWorkers.length : 1,
                  eligibleCount: (request.candidateWorkers && request.candidateWorkers.length > 0) ? request.candidateWorkers.length : 1,
                  filteredCount: 0,
                  competitiveCount: Math.min((request.candidateWorkers && request.candidateWorkers.length > 0) ? request.candidateWorkers.length : 1, 3),
                  selectedModel: executedModel,
                }}
                decisionReason={request.decisionReason}
                candidateWorkers={request.candidateWorkers}
              />
            </div>
          )}

          {activeTab === "execution" && (
            <div className="drawer-section">
              <div className="drawer-section-title">Execution Trace</div>
              <ExecutionTrace totalMs={request.latencyMs} />
            </div>
          )}

          {activeTab === "timeline" && (
            <div className="drawer-section">
              <div className="drawer-section-title">Database-Authoritative Event History</div>
              {realTimeline?.events && realTimeline.events.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {realTimeline.events.map((ev: any) => (
                    <div
                      key={ev.id || ev.logical_sequence}
                      style={{
                        backgroundColor: "var(--bg-elevated)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-xs)",
                        padding: "0.5rem 0.75rem",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "0.75rem",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-tertiary)", minWidth: "2rem" }}>
                          #{ev.logical_sequence}
                        </span>
                        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{ev.event_type}</span>
                        {ev.task_id && (
                          <span style={{ fontSize: "0.6875rem", fontFamily: "var(--font-mono)", color: "var(--accent)" }}>
                            [{ev.task_id}]
                          </span>
                        )}
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                        {new Date(ev.timestamp).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>No events recorded for this workflow.</div>
              )}
            </div>
          )}

          {activeTab === "replay" && (
            <div className="drawer-section">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="drawer-section-title">Deterministic Replay Engine</span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleFetchReplay}
                  disabled={replayLoading}
                >
                  <RotateCcw size={12} className={replayLoading ? "animate-spin" : ""} />
                  <span>{replayLoading ? "Replaying..." : "Run Replay"}</span>
                </button>
              </div>

              {replayData ? (
                <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div
                    style={{
                      padding: "0.75rem",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: replayData.replay_valid ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
                      border: `1px solid ${replayData.replay_valid ? "var(--success)" : "var(--error)"}`,
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    {replayData.replay_valid ? (
                      <CheckCircle2 size={16} style={{ color: "var(--success)" }} />
                    ) : (
                      <XCircle size={16} style={{ color: "var(--error)" }} />
                    )}
                    <span style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
                      {replayData.replay_valid ? "Deterministic Replay Succeeded" : "Replay Divergence Detected"}
                    </span>
                  </div>

                  <div className="info-grid">
                    <div className="info-row">
                      <span className="info-label">Reconstructed Status</span>
                      <span className="info-val font-mono">{replayData.reconstructed_status}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Live DB Status</span>
                      <span className="info-val font-mono">{replayData.current_status}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Applied Events Count</span>
                      <span className="info-val font-mono">{replayData.applied_events_count}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Reconstructed Tasks</span>
                      <span className="info-val font-mono">{replayData.comparison?.tasks_count ?? 0}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ color: "var(--text-tertiary)", fontSize: "0.75rem", marginTop: "0.5rem" }}>
                  Click "Run Replay" to verify deterministic event replay against live state.
                </div>
              )}
            </div>
          )}

          {activeTab === "tokens" && (
            <div className="drawer-section">
              <div className="drawer-section-title">Token Accounting & Costs</div>
              <div className="info-grid">
                <div className="info-row">
                  <span className="info-label">Prompt Tokens</span>
                  <span className="info-val">{request.tokens.input.toLocaleString()}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Completion Tokens</span>
                  <span className="info-val">{request.tokens.output.toLocaleString()}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Total Tokens</span>
                  <span className="info-val" style={{ fontWeight: 600 }}>{request.tokens.total.toLocaleString()}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Actual Incurred Cost</span>
                  <span className="info-val" style={{ color: "var(--success)", fontWeight: 600 }}>
                    ${(request.cost || 0).toFixed(4)} {request.isFreeTier !== false ? "(Autonomous Route)" : ""}
                  </span>
                </div>
                <div className="info-row">
                  <span className="info-label">Commercial Market Value</span>
                  <span className="info-val font-mono" style={{ color: "var(--text-primary)" }}>
                    ${(request.commercialCost !== undefined ? request.commercialCost : ((request.tokens.input * 0.0000025) + (request.tokens.output * 0.0000100))).toFixed(4)}
                  </span>
                </div>
                <div className="info-row">
                  <span className="info-label">Capital Value Saved</span>
                  <span className="info-val font-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>
                    ${(request.savedCost !== undefined ? request.savedCost : (request.commercialCost || 0)).toFixed(4)}
                  </span>
                </div>
                <div className="info-row">
                  <span className="info-label">Time to First Token</span>
                  <span className="info-val">{request.ttftMs}ms</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Total Latency</span>
                  <span className="info-val">{request.latencyMs}ms</span>
                </div>
              </div>
            </div>
          )}

          {activeTab === "raw" && (
            <div className="drawer-section">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="drawer-section-title">Raw Telemetry & Analytics Payload</span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleCopyRaw}
                >
                  {copied ? <Check size={12} style={{ color: "var(--success)" }} /> : <Copy size={12} />}
                  <span>{copied ? "Copied" : "Copy JSON"}</span>
                </button>
              </div>
              <pre style={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", padding: "0.75rem", fontSize: "0.6875rem", overflowX: "auto", maxHeight: "400px" }}>
                {JSON.stringify({ ...request, liveMetrics: realMetrics, eventTimeline: realTimeline, replay: replayData }, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
