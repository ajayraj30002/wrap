import { useState, useEffect, useCallback } from "react";
import { Activity, Zap, Layers, Server, DollarSign, CheckCircle2, RefreshCw } from "lucide-react";
import { apiClient } from "../lib/apiClient";
import { getProviderBadgeStyle } from "../lib/providerBadges";

interface CachedAnalyticsState {
  routingDistribution: Array<{ name: string; pct: number; color: string }>;
  modelsData: any[];
  providersData: any[];
  tokensData: {
    total: string;
    input: string;
    output: string;
    actualCost: string;
    commercialSaved: string;
    savingsPct: string;
    benchmark: string;
  } | null;
  points: Array<{ time: string; p50: number; p95: number; ttft: number; tps: number }>;
  workflowSummary: any | null;
}

function getInitialAnalytics(): CachedAnalyticsState | null {
  try {
    const raw = sessionStorage.getItem("wrap_cached_analytics");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

let cachedAnalytics: CachedAnalyticsState | null = getInitialAnalytics();

export function Analytics() {
  const [timeRange, setTimeRange] = useState<"1h" | "24h" | "7d" | "30d">("24h");
  const [latencyMetric, setLatencyMetric] = useState<"p50" | "p95" | "TTFT" | "TPS">("p50");
  const [breakdownView, setBreakdownView] = useState<"models" | "providers">("models");

  const [loading, setLoading] = useState(!cachedAnalytics);
  const [hoveredPoint, setHoveredPoint] = useState<{ x: number; y: number; time: string; val: number } | null>(null);
  const [routingDistribution, setRoutingDistribution] = useState<Array<{ name: string; pct: number; color: string }>>(cachedAnalytics?.routingDistribution || []);
  const [modelsData, setModelsData] = useState<any[]>(cachedAnalytics?.modelsData || []);
  const [providersData, setProvidersData] = useState<any[]>(cachedAnalytics?.providersData || []);

  const [tokensData, setTokensData] = useState<{
    total: string;
    input: string;
    output: string;
    actualCost: string;
    commercialSaved: string;
    savingsPct: string;
    benchmark: string;
  } | null>(cachedAnalytics?.tokensData || null);

  const [points, setPoints] = useState<Array<{ time: string; p50: number; p95: number; ttft: number; tps: number }>>(cachedAnalytics?.points || []);
  const [workflowSummary, setWorkflowSummary] = useState<any | null>(cachedAnalytics?.workflowSummary || null);

  const fetchAnalytics = useCallback(async (selectedRange?: "1h" | "24h" | "7d" | "30d", isManualRefresh = false) => {
    const rangeToFetch = selectedRange || timeRange;
    if (!cachedAnalytics || isManualRefresh) {
      setLoading(true);
    }
    try {
      const data = await apiClient.get(`/api/dashboard/analytics?range=${rangeToFetch}`, {
        bypassCache: isManualRefresh,
      });
      if (data) {
        if (data.workflow_summary) {
          setWorkflowSummary(data.workflow_summary);
        }
        if (Array.isArray(data.models)) {
          setModelsData(data.models);
        }
        if (Array.isArray(data.providers)) {
          setProvidersData(data.providers);
        }
        if (data.tokens) {
          setTokensData(data.tokens);
        }
        if (Array.isArray(data.routing_distribution)) {
          setRoutingDistribution(data.routing_distribution);
        }
        if (Array.isArray(data.timeseries)) {
          setPoints(data.timeseries);
        }

        cachedAnalytics = {
          routingDistribution: Array.isArray(data.routing_distribution) ? data.routing_distribution : (cachedAnalytics?.routingDistribution || []),
          modelsData: Array.isArray(data.models) ? data.models : (cachedAnalytics?.modelsData || []),
          providersData: Array.isArray(data.providers) ? data.providers : (cachedAnalytics?.providersData || []),
          tokensData: data.tokens || cachedAnalytics?.tokensData || null,
          points: Array.isArray(data.timeseries) ? data.timeseries : (cachedAnalytics?.points || []),
          workflowSummary: data.workflow_summary || cachedAnalytics?.workflowSummary || null,
        };
        try {
          sessionStorage.setItem("wrap_cached_analytics", JSON.stringify(cachedAnalytics));
        } catch {}
      }
    } catch (e) {
      console.error("Analytics fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchAnalytics(timeRange);
  }, [fetchAnalytics, timeRange]);

  const currentAvg = points.length > 0 ? Math.round(
    points.reduce((acc, p) => {
      const val = latencyMetric === "p50" ? p.p50 : latencyMetric === "p95" ? p.p95 : latencyMetric === "TTFT" ? p.ttft : p.tps;
      return acc + val;
    }, 0) / points.length
  ) : 0;

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Activity size={18} style={{ color: "var(--accent)" }} />
            <span>Operational Analytics & DAG Efficiency</span>
          </h1>
          <p className="page-subtitle">
            Routing distribution, latency percentiles, and measured DAG acceleration speedup
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="time-range-group">
            {(["1h", "24h", "7d", "30d"] as const).map((r) => (
              <button
                key={r}
                className={`time-range-btn ${timeRange === r ? "active" : ""}`}
                onClick={() => {
                  setTimeRange(r);
                  fetchAnalytics(r);
                }}
              >
                {r}
              </button>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => fetchAnalytics(timeRange, true)} disabled={loading} title="Refresh analytics">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Top Grid: Real Auto Routing Distribution & Latency Behavior */}
      <div className="analytics-grid-two-col">
        {/* Horizontal Distribution Visualization */}
        <div className="analytics-distribution-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-tertiary)" }}>
              Routing Distribution (By Provider)
            </span>
            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
              <span className="dag-live-dot" style={{ width: "5px", height: "5px" }} />
              <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                Active Telemetry
              </span>
            </div>
          </div>

          {/* Segmented Distribution Bar (Pill style with micro-gaps) */}
          {routingDistribution.length > 0 && (
            <div style={{ display: "flex", height: "10px", borderRadius: "9999px", overflow: "hidden", margin: "0.25rem 0", backgroundColor: "var(--bg-subtle)", gap: "2px", padding: "1px" }}>
              {routingDistribution.map((item) => {
                const badge = getProviderBadgeStyle(item.name);
                const color = badge.dot || item.color || "var(--accent)";
                return (
                  <div
                    key={item.name}
                    style={{
                      width: `${item.pct}%`,
                      backgroundColor: color,
                      borderRadius: "9999px",
                      transition: "width 0.4s ease",
                      boxShadow: `0 0 6px ${color}44`,
                    }}
                    title={`${item.name}: ${item.pct}%`}
                  />
                );
              })}
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginTop: "0.25rem" }}>
            {loading && routingDistribution.length === 0 ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="dist-bar-row">
                  <span className="skeleton-shimmer skeleton-line" style={{ width: "65px" }} />
                  <div className="dist-track">
                    <div className="skeleton-shimmer" style={{ width: `${70 - i * 20}%`, height: "100%" }} />
                  </div>
                  <span className="skeleton-shimmer skeleton-line" style={{ width: "24px" }} />
                </div>
              ))
            ) : routingDistribution.length === 0 ? (
              <div style={{ padding: "1.5rem 0", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                No provider routing telemetry recorded yet
              </div>
            ) : (
              routingDistribution.map((item) => {
                const badge = getProviderBadgeStyle(item.name);
                const brandColor = badge.dot || item.color || "var(--accent)";

                return (
                  <div
                    key={item.name}
                    className="dist-bar-row fade-in"
                    style={{
                      padding: "0.45rem 0.65rem",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "var(--bg-elevated)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "110px", flexShrink: 0 }}>
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          backgroundColor: brandColor,
                          boxShadow: `0 0 6px ${brandColor}88`,
                          flexShrink: 0,
                        }}
                      />
                      <span className="dist-label font-mono" style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.75rem" }}>
                        {item.name}
                      </span>
                    </div>

                    <div className="dist-track" style={{ height: "6px", backgroundColor: "var(--bg-subtle)" }}>
                      <div
                        className="dist-fill"
                        style={{
                          width: `${item.pct}%`,
                          background: `linear-gradient(90deg, ${brandColor}, ${brandColor}bb)`,
                          borderRadius: "9999px",
                          boxShadow: `0 0 6px ${brandColor}55`,
                          transition: "width 0.4s ease",
                        }}
                      />
                    </div>

                    <span className="dist-val font-mono" style={{ color: "var(--text-primary)", fontWeight: 700 }}>
                      {item.pct}%
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Latency Behavior & Percentile Toggle */}
        <div className="analytics-distribution-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-tertiary)" }}>
                Latency Behavior
              </span>
              <span
                style={{
                  fontSize: "0.6875rem",
                  fontFamily: "var(--font-mono)",
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-xs)",
                  padding: "0.1rem 0.4rem",
                  color: "var(--text-primary)",
                  fontWeight: 600,
                }}
              >
                Avg: <span style={{ color: "var(--accent)" }}>{currentAvg}{latencyMetric === "TPS" ? " tok/s" : "ms"}</span>
              </span>
            </div>
            <div className="filter-btn-group">
              {(["p50", "p95", "TTFT", "TPS"] as const).map((m) => (
                <button
                  key={m}
                  className={`filter-btn ${latencyMetric === m ? "active" : ""}`}
                  onClick={() => setLatencyMetric(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {/* SVG Smooth Curved Area Chart */}
          <div style={{ height: "135px", width: "100%", marginTop: "0.25rem", position: "relative" }} onMouseLeave={() => setHoveredPoint(null)}>
            {loading && points.length === 0 ? (
              <div className="skeleton-shimmer" style={{ width: "100%", height: "115px", borderRadius: "var(--radius-sm)" }} />
            ) : points.length === 0 ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "115px", color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                <span>Awaiting live request latency time-series samples...</span>
              </div>
            ) : (
              (() => {
                const getVal = (p: typeof points[0]) => (latencyMetric === "p50" ? p.p50 : latencyMetric === "p95" ? p.p95 : latencyMetric === "TTFT" ? p.ttft : p.tps);
                const vals = points.map(getVal);
                const minVal = Math.min(...vals);
                const maxVal = Math.max(...vals, minVal + 1);
                const pts = points.map((p, idx) => {
                  const x = points.length === 1 ? 200 : 20 + (idx / (points.length - 1)) * 360;
                  const y = 92 - ((getVal(p) - minVal) / (maxVal - minVal)) * 68;
                  return { x, y, time: p.time, val: getVal(p) };
                });

                // Smooth cubic bezier path generation
                let pathD = `M ${pts[0].x} ${pts[0].y}`;
                for (let i = 0; i < pts.length - 1; i++) {
                  const curr = pts[i];
                  const next = pts[i + 1];
                  const midX = (curr.x + next.x) / 2;
                  pathD += ` C ${midX} ${curr.y}, ${midX} ${next.y}, ${next.x} ${next.y}`;
                }
                const areaD = `${pathD} L ${pts[pts.length - 1].x} 115 L ${pts[0].x} 115 Z`;

                // Smart deduplicated time markers (preventing 00:00 00:00 repeated clusters)
                const areAllSameTime = points.every((p) => p.time === points[0]?.time);
                const displayXLabels = areAllSameTime
                  ? [
                      { label: "Window Start", x: 20 },
                      { label: points[0]?.time || "Recent", x: 200 },
                      { label: "Now", x: 380 },
                    ]
                  : [
                      { label: points[0]?.time || "", x: pts[0]?.x || 20 },
                      ...(points.length > 2
                        ? [{ label: points[Math.floor(points.length / 2)]?.time || "", x: pts[Math.floor(points.length / 2)]?.x || 200 }]
                        : []),
                      { label: points[points.length - 1]?.time || "", x: pts[pts.length - 1]?.x || 380 },
                    ];

                return (
                  <div className="fade-in" style={{ position: "relative", width: "100%", height: "100%" }}>
                    {/* Hover Floating Tooltip */}
                    {hoveredPoint && (
                      <div
                        style={{
                          position: "absolute",
                          left: `${(hoveredPoint.x / 400) * 100}%`,
                          top: `${Math.max(0, hoveredPoint.y - 28)}px`,
                          transform: "translateX(-50%)",
                          backgroundColor: "var(--bg-elevated)",
                          border: "1px solid var(--accent-border)",
                          borderRadius: "var(--radius-xs)",
                          padding: "0.15rem 0.45rem",
                          fontSize: "0.6875rem",
                          fontFamily: "var(--font-mono)",
                          color: "var(--text-primary)",
                          boxShadow: "0 4px 14px rgba(0,0,0,0.4)",
                          pointerEvents: "none",
                          zIndex: 10,
                          whiteSpace: "nowrap",
                        }}
                      >
                        <span style={{ color: "var(--accent)", fontWeight: 700 }}>
                          {hoveredPoint.val}{latencyMetric === "TPS" ? " tok/s" : "ms"}
                        </span>
                        <span style={{ color: "var(--text-tertiary)", marginLeft: "0.35rem" }}>
                          ({hoveredPoint.time})
                        </span>
                      </div>
                    )}

                    <svg width="100%" height="115" viewBox="0 0 400 115" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="metricGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.32" />
                          <stop offset="80%" stopColor="var(--accent)" stopOpacity="0.04" />
                          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.0" />
                        </linearGradient>
                      </defs>

                      {/* Subtle Grid Guidelines */}
                      <line x1="20" y1="24" x2="380" y2="24" stroke="var(--border-subtle)" strokeDasharray="3 3" opacity="0.6" />
                      <line x1="20" y1="58" x2="380" y2="58" stroke="var(--border-subtle)" strokeDasharray="3 3" opacity="0.6" />
                      <line x1="20" y1="92" x2="380" y2="92" stroke="var(--border-subtle)" strokeDasharray="3 3" opacity="0.6" />

                      <path d={areaD} fill="url(#metricGrad)" />
                      <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" />

                      {/* Interactive Data Dots on Curve */}
                      {pts.map((pt, idx) => (
                        <circle
                          key={idx}
                          cx={pt.x}
                          cy={pt.y}
                          r={hoveredPoint?.time === pt.time ? "5" : "3.5"}
                          fill="var(--bg-surface)"
                          stroke="var(--accent)"
                          strokeWidth="2"
                          style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                          onMouseEnter={() => setHoveredPoint(pt)}
                        />
                      ))}
                    </svg>

                    {/* Clean Deduplicated Time Axis */}
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6875rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", marginTop: "0.15rem", padding: "0 0.5rem" }}>
                      {displayXLabels.map((item, idx) => (
                        <span key={idx}>{item.label}</span>
                      ))}
                    </div>
                  </div>
                );
              })()
            )}
          </div>
        </div>
      </div>

      {/* DAG EXECUTION EFFICIENCY (SIGNATURE WRAP DIFFERENTIATOR) */}
      <div className="dag-efficiency-panel">
        <div className="dag-efficiency-accent-glow" />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "var(--accent-muted)",
                border: "1px solid var(--accent-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent)",
                flexShrink: 0,
              }}
            >
              <Zap size={16} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                  Measured DAG Orchestration Efficiency
                </span>
                <span
                  style={{
                    fontSize: "0.5625rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    padding: "0.15rem 0.45rem",
                    borderRadius: "9999px",
                    backgroundColor: "rgba(56, 189, 248, 0.12)",
                    color: "var(--accent)",
                    border: "1px solid var(--accent-border)",
                    letterSpacing: "0.04em",
                  }}
                >
                  AUTONOMOUS TOPOLOGY
                </span>
              </div>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: "0.15rem 0 0" }}>
                Parallel speedup over standard sequential execution, critical path analysis & zero retry overhead
              </p>
            </div>
          </div>
        </div>

        {/* Speedup Metric Cards */}
        <div className="efficiency-grid">
          <div className="efficiency-card">
            <span className="efficiency-label">Single-Task Baseline</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem" }}>
              <span className="efficiency-val font-mono" style={{ color: "var(--text-tertiary)" }}>1.00x</span>
            </div>
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>standard sequential baseline</span>
          </div>

          <div className="efficiency-card hero">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="efficiency-label" style={{ color: "var(--accent)", fontWeight: 700 }}>
                DAG Parallelism Factor
              </span>
              <span style={{ fontSize: "0.5625rem", padding: "0.1rem 0.35rem", borderRadius: "9999px", backgroundColor: "var(--accent-muted)", color: "var(--accent)", fontWeight: 600 }}>
                SPEEDUP
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.35rem" }}>
              <span className="efficiency-val font-mono text-accent" style={{ fontSize: "1.5rem" }}>
                {(workflowSummary?.average_parallelism_factor ?? workflowSummary?.avg_parallelism_factor)
                  ? `${workflowSummary?.average_parallelism_factor ?? workflowSummary?.avg_parallelism_factor}x`
                  : "1.00x"}
              </span>
            </div>
            <span style={{ fontSize: "0.625rem", color: "var(--text-secondary)" }}>
              {(workflowSummary?.total_workflows ?? workflowSummary?.total_runs)
                ? `${workflowSummary?.total_workflows ?? workflowSummary?.total_runs} recorded runs`
                : "measured multi-agent split"}
            </span>
          </div>

          {(() => {
            const completedCount = workflowSummary?.completed_workflows ?? workflowSummary?.completed_runs ?? 0;
            const failedCount = workflowSummary?.failed_workflows ?? workflowSummary?.failed_runs ?? 0;
            const totalRecorded = workflowSummary?.total_workflows ?? workflowSummary?.total_runs ?? 0;
            const finishedCount = completedCount + failedCount;
            const successPct = finishedCount > 0 ? Math.round((completedCount / finishedCount) * 100) : 100;

            return (
              <div
                className="efficiency-card"
                title={`Historical DAG Run Breakdown:\n• ${completedCount} Successful\n• ${failedCount} Failed (initial setup/testing)\n• ${Math.max(0, totalRecorded - finishedCount)} Partial / In-flight\nTotal Recorded: ${totalRecorded}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="efficiency-label">Completed Runs</span>
                  <span
                    className={`status-dot ${failedCount > 0 ? "degraded" : "healthy"}`}
                    title={failedCount > 0 ? `${failedCount} historical failed runs detected` : "All runs successful"}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.45rem" }}>
                  <span className="efficiency-val font-mono" style={{ color: "var(--success)" }}>
                    {completedCount}
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                    / {finishedCount || totalRecorded}
                  </span>
                </div>
                <span style={{ fontSize: "0.625rem", color: failedCount > 0 ? "var(--warning)" : "var(--text-tertiary)" }}>
                  {failedCount > 0 ? `${successPct}% success rate (${failedCount} failed)` : "100% execution success"}
                </span>
              </div>
            );
          })()}

          <div className="efficiency-card">
            <span className="efficiency-label">Mean Wall-Clock Latency</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem" }}>
              <span className="efficiency-val font-mono text-primary">
                {(workflowSummary?.average_wall_clock_ms ?? workflowSummary?.avg_wall_clock_duration_ms)
                  ? `${((workflowSummary?.average_wall_clock_ms ?? workflowSummary?.avg_wall_clock_duration_ms) / 1000).toFixed(2)}s`
                  : "0.0s"}
              </span>
            </div>
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>total end-to-end work</span>
          </div>
        </div>

        {/* Micro-metric Strip (Orchestration Decomposition) */}
        <div className="dag-decomp-strip">
          <div className="decomp-tile">
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
              Critical Path
            </span>
            <span className="font-mono text-primary" style={{ fontSize: "0.875rem", fontWeight: 600 }}>
              {(workflowSummary?.average_critical_path_ms ?? workflowSummary?.avg_critical_path_duration_ms)
                ? `${((workflowSummary?.average_critical_path_ms ?? workflowSummary?.avg_critical_path_duration_ms) / 1000).toFixed(2)}s`
                : "0.0s"}
            </span>
          </div>

          <div className="decomp-tile">
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
              Task Attempts
            </span>
            <span className="font-mono text-primary" style={{ fontSize: "0.875rem", fontWeight: 600 }}>
              {workflowSummary?.total_attempts ?? workflowSummary?.total_workflows ?? workflowSummary?.total_runs ?? 0}
            </span>
          </div>

          <div className="decomp-tile">
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
              Computational Pool
            </span>
            <span className="font-mono text-primary" style={{ fontSize: "0.875rem", fontWeight: 600 }}>
              {routingDistribution.length} provider{routingDistribution.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="decomp-tile">
            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
              Retry Overhead
            </span>
            <span className="font-mono" style={{ fontSize: "0.875rem", fontWeight: 600, color: (workflowSummary?.total_retries || 0) > 0 ? "var(--warning)" : "var(--success)" }}>
              {workflowSummary?.total_retries ?? 0} retries ({(((workflowSummary?.retry_rate ?? 0)) * 100).toFixed(1)}%)
            </span>
          </div>
        </div>
      </div>

      {/* Real Token Accounting & Cost Breakdown */}
      <div className="analytics-grid-two-col">
        {!tokensData ? (
          Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="operational-card">
              <div className="op-card-header">
                <span className="skeleton-shimmer skeleton-line" style={{ width: "130px" }} />
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "40px", height: "14px" }} />
              </div>
              <div className="op-card-main">
                <span className="skeleton-shimmer skeleton-metric-block" style={{ width: "75px", height: "26px" }} />
                <span className="skeleton-shimmer skeleton-line" style={{ width: "40px", marginTop: "4px" }} />
              </div>
              <div className="op-card-footer">
                <span className="skeleton-shimmer skeleton-line" style={{ width: "110px" }} />
                <span className="skeleton-shimmer skeleton-line" style={{ width: "110px" }} />
              </div>
            </div>
          ))
        ) : (
          <>
            <div className="operational-card fade-in" style={{ padding: "1.15rem 1.25rem", borderRadius: "var(--radius-lg)" }}>
              <div className="op-card-header">
                <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.05em", color: "var(--text-tertiary)" }}>
                  TOTAL TOKENS PROCESSED
                </span>
                <span className="op-card-trend font-mono" style={{ color: "var(--accent)", backgroundColor: "var(--accent-muted)", padding: "0.1rem 0.4rem", borderRadius: "var(--radius-xs)" }}>
                  Live Stream
                </span>
              </div>
              <div className="op-card-main" style={{ margin: "0.35rem 0" }}>
                <span className="op-card-val font-mono" style={{ fontSize: "1.75rem", fontWeight: 700 }}>{tokensData.total}</span>
                <span className="text-secondary font-mono text-xs" style={{ marginLeft: "0.35rem" }}>tokens</span>
              </div>

              {/* Visual Split Ratio Bar between Input and Output */}
              {(() => {
                const inNum = parseFloat(tokensData.input.replace(/k/g, "")) || 1;
                const outNum = parseFloat(tokensData.output.replace(/k/g, "")) || 0;
                const totalNum = inNum + outNum || 1;
                const inPct = Math.round((inNum / totalNum) * 100);
                const outPct = 100 - inPct;

                return (
                  <div style={{ margin: "0.5rem 0 0.25rem" }}>
                    <div style={{ display: "flex", height: "6px", borderRadius: "9999px", overflow: "hidden", backgroundColor: "var(--bg-subtle)", gap: "2px" }}>
                      <div style={{ width: `${inPct}%`, backgroundColor: "var(--accent)", borderRadius: "9999px", transition: "width 0.4s ease" }} title={`Prompt: ${inPct}%`} />
                      <div style={{ width: `${outPct}%`, backgroundColor: "var(--success)", borderRadius: "9999px", transition: "width 0.4s ease" }} title={`Completion: ${outPct}%`} />
                    </div>
                  </div>
                );
              })()}

              <div className="op-card-footer" style={{ borderTop: "none", paddingTop: "0.25rem" }}>
                <span style={{ fontSize: "0.6875rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "var(--accent)" }} />
                  Prompt: <strong className="font-mono text-primary">{tokensData.input}</strong>
                </span>
                <span style={{ fontSize: "0.6875rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "var(--success)" }} />
                  Completion: <strong className="font-mono text-primary">{tokensData.output}</strong>
                </span>
              </div>
            </div>

            <div className="operational-card fade-in" style={{ padding: "1.15rem 1.25rem", borderRadius: "var(--radius-lg)" }}>
              <div className="op-card-header">
                <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.05em", color: "var(--text-tertiary)" }}>
                  CAPITAL ECONOMICS
                </span>
                <span className="op-card-trend font-mono" style={{ color: "var(--success)", backgroundColor: "var(--success-muted)", border: "1px solid var(--success-border)", padding: "0.1rem 0.45rem", borderRadius: "9999px", fontWeight: 700 }}>
                  {tokensData.savingsPct}
                </span>
              </div>
              <div className="op-card-main" style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", margin: "0.35rem 0" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.35rem" }}>
                  <span className="op-card-val font-mono" style={{ color: "var(--success)", fontSize: "1.75rem", fontWeight: 700 }}>
                    +{tokensData.commercialSaved}
                  </span>
                  <span className="font-mono text-xs" style={{ color: "var(--success)", fontWeight: 600 }}>saved</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.25rem" }}>
                  <span className="font-mono" style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                    {tokensData.actualCost}
                  </span>
                  <span className="text-muted font-mono text-xs">spend</span>
                </div>
              </div>
              <div className="op-card-footer" style={{ borderTop: "none", paddingTop: "0.25rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.6875rem" }}>
                  Window: <strong className="font-mono text-primary">{timeRange}</strong>
                </span>
                <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }} title="Calculated against standard commercial model market benchmark">
                  vs {tokensData.benchmark}
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* GRANULAR TOKEN ECONOMICS & ACCURATE PRICING MATRIX */}
      <div
        style={{
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          padding: "1rem",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <DollarSign size={16} style={{ color: "var(--success)" }} />
            <div>
              <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Model & Provider Token Economics
              </span>
              <p style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", margin: 0 }}>
                Granular prompt and completion token accounting, unit pricing ($/1M), and capital savings
              </p>
            </div>
          </div>

          <div className="filter-btn-group">
            <button
              className={`filter-btn ${breakdownView === "models" ? "active" : ""}`}
              onClick={() => setBreakdownView("models")}
            >
              <Layers size={12} style={{ marginRight: "0.25rem", display: "inline" }} />
              BY MODEL ({modelsData.length})
            </button>
            <button
              className={`filter-btn ${breakdownView === "providers" ? "active" : ""}`}
              onClick={() => setBreakdownView("providers")}
            >
              <Server size={12} style={{ marginRight: "0.25rem", display: "inline" }} />
              BY PROVIDER ({providersData.length})
            </button>
          </div>
        </div>

        {/* Telemetry Table */}
        <div className="dense-table-wrapper" style={{ maxHeight: "420px" }}>
          {breakdownView === "models" ? (
            <table className="dense-table dense-table-wide">
              <thead>
                <tr>
                  <th>Model Identifier</th>
                  <th>Provider</th>
                  <th>Executions</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>Total Tokens</th>
                  <th title="Actual billed out-of-pocket cost charged by the routed provider ($0.00 for developer free tier).">
                    Direct Spend
                  </th>
                  <th title="Commercial market baseline (e.g. OpenAI equivalent) used solely to calculate Capital Saved. This is NOT what you were charged.">
                    Savings Benchmark ($/1M)
                  </th>
                  <th title="Net commercial savings delivered by WRAP: (Tokens × Benchmark Rate) - Direct Spend.">
                    Capital Saved
                  </th>
                  <th>Avg Latency</th>
                  <th>Reliability</th>
                </tr>
              </thead>
              <tbody>
                {modelsData.map((m) => (
                  <tr key={`${m.provider}-${m.model}`}>
                    <td className="font-mono text-primary" style={{ fontWeight: 600 }}>
                      {m.model}
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.15rem 0.4rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor: "var(--bg-subtle)",
                          border: "1px solid var(--border-subtle)",
                          fontFamily: "var(--font-mono)",
                          textTransform: "uppercase",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {m.provider}
                      </span>
                    </td>
                    <td className="font-mono text-secondary">{m.requests}</td>
                    <td className="font-mono">{m.input_tokens.toLocaleString()}</td>
                    <td className="font-mono">{m.output_tokens.toLocaleString()}</td>
                    <td className="font-mono text-primary" style={{ fontWeight: 600 }}>
                      {m.tokens.toLocaleString()}
                    </td>
                    <td className="font-mono">
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>
                        ${m.cost.toFixed(4)}
                      </span>
                      {m.is_free_tier && (
                        <span
                          style={{
                            marginLeft: "0.25rem",
                            fontSize: "0.625rem",
                            padding: "0.1rem 0.25rem",
                            borderRadius: "2px",
                            backgroundColor: "var(--success-muted)",
                            color: "var(--success)",
                          }}
                        >
                          FREE
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: "0.6875rem", color: "var(--text-secondary)" }}>
                      <span className="font-mono text-primary">{m.benchmark_model}</span>
                      <span className="font-mono" style={{ color: "var(--text-tertiary)", marginLeft: "0.25rem" }}>
                        (${m.benchmark_rates?.input_per_m?.toFixed(2)} / ${m.benchmark_rates?.output_per_m?.toFixed(2)})
                      </span>
                    </td>
                    <td className="font-mono">
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>
                        +${m.saved_cost.toFixed(4)}
                      </span>
                    </td>
                    <td className="font-mono text-secondary">{m.avg_latency_ms}ms</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <CheckCircle2 size={12} style={{ color: "var(--success)" }} />
                        <span className="font-mono" style={{ fontSize: "0.6875rem", color: "var(--success)" }}>
                          {m.success_rate}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
                {modelsData.length === 0 && (
                  <tr>
                    <td colSpan={11} style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)" }}>
                      No executed model data recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="dense-table dense-table-wide">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Routed Operations</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>Total Tokens</th>
                  <th>Direct Billed Spend</th>
                  <th>Commercial Benchmark Value</th>
                  <th>Net Capital Saved</th>
                  <th>Mean Latency</th>
                  <th>Routing Status</th>
                </tr>
              </thead>
              <tbody>
                {providersData.map((p) => (
                  <tr key={p.provider}>
                    <td className="font-mono text-primary" style={{ fontWeight: 600 }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          padding: "0.2rem 0.5rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor: "var(--bg-subtle)",
                          border: "1px solid var(--border-default)",
                          textTransform: "uppercase",
                          color: "var(--accent)",
                        }}
                      >
                        {p.provider}
                      </span>
                    </td>
                    <td className="font-mono text-secondary">{p.requests}</td>
                    <td className="font-mono">{p.input_tokens.toLocaleString()}</td>
                    <td className="font-mono">{p.output_tokens.toLocaleString()}</td>
                    <td className="font-mono text-primary" style={{ fontWeight: 600 }}>
                      {p.tokens.toLocaleString()}
                    </td>
                    <td className="font-mono">
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>
                        ${p.cost.toFixed(4)}
                      </span>
                    </td>
                    <td className="font-mono text-secondary">
                      ${p.commercial_cost.toFixed(4)}
                    </td>
                    <td className="font-mono">
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>
                        +${p.saved_cost.toFixed(4)}
                      </span>
                    </td>
                    <td className="font-mono text-secondary">{p.avg_latency_ms}ms</td>
                    <td>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.15rem 0.4rem",
                          borderRadius: "2px",
                          backgroundColor: "var(--success-muted)",
                          border: "1px solid var(--success-border)",
                          color: "var(--success)",
                          fontWeight: 500,
                        }}
                      >
                        100% Free Quota Routed
                      </span>
                    </td>
                  </tr>
                ))}
                {providersData.length === 0 && (
                  <tr>
                    <td colSpan={10} style={{ textAlign: "center", padding: "2rem", color: "var(--text-tertiary)" }}>
                      No provider routing data recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
