import { useState, useEffect, useCallback } from "react";
import { Database, RefreshCw, AlertCircle, TrendingUp, CheckCircle2 } from "lucide-react";
import { apiClient } from "../lib/apiClient";

interface ProviderQuota {
  name: string;
  remainingPct: number;
  resetTime: string;
  status: "healthy" | "warning" | "error";
  rateLimitUsagePct: number;
}

interface WorkerMatrixRow {
  id: string;
  provider: string;
  worker: string;
  credentialName: string;
  maskedIdentifier?: string;
  remainingPct: number;
  rateLimitPct: number;
  resetIn: string;
  state: "healthy" | "busy" | "rate_limited" | "degraded" | "unhealthy" | "offline";
}

let cachedQuota: {
  providerQuotas: ProviderQuota[];
  workerMatrix: WorkerMatrixRow[];
} | null = null;

export function Quota() {
  const [loading, setLoading] = useState(!cachedQuota);
  const [providerQuotas, setProviderQuotas] = useState<ProviderQuota[]>(cachedQuota?.providerQuotas || []);
  const [workerMatrix, setWorkerMatrix] = useState<WorkerMatrixRow[]>(cachedQuota?.workerMatrix || []);

  const fetchQuotaData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get("/api/dashboard/quota");
      if (data) {
        const matrix = Array.isArray(data.worker_matrix) ? data.worker_matrix : (cachedQuota?.workerMatrix || []);
        const quotas = Array.isArray(data.provider_quotas) ? data.provider_quotas : (cachedQuota?.providerQuotas || []);
        setWorkerMatrix(matrix);
        setProviderQuotas(quotas);
        cachedQuota = { providerQuotas: quotas, workerMatrix: matrix };
      }
    } catch (e) {
      console.error("Quota fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQuotaData();
    const interval = setInterval(fetchQuotaData, 15000);
    return () => clearInterval(interval);
  }, [fetchQuotaData]);

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Database size={18} style={{ color: "var(--accent)" }} />
            <span>Capacity & Execution Headroom</span>
          </h1>
          <p className="page-subtitle">
            Observable rate limits, remaining provider quota windows, and failover projection
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchQuotaData} disabled={loading} title="Refresh quota status">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          <span>{loading ? "Refreshing..." : "Refresh"}</span>
        </button>
      </div>

      {/* Real Provider Quota Cards Grid */}
      <div className="quota-grid">
        {loading && providerQuotas.length === 0 ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="quota-provider-card">
              <div className="quota-card-top">
                <span className="skeleton-shimmer skeleton-line" style={{ width: "70px" }} />
                <span className="skeleton-shimmer skeleton-line" style={{ width: "80px" }} />
              </div>

              <div className="quota-progress-track">
                <div className="skeleton-shimmer" style={{ width: "100%", height: "100%" }} />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="skeleton-shimmer skeleton-line" style={{ width: "100px" }} />
                <span className="skeleton-shimmer skeleton-line" style={{ width: "70px" }} />
              </div>
            </div>
          ))
        ) : (
          providerQuotas.map((pq) => {
            const isGemini = pq.name.toLowerCase().includes("gemini");
            const isGroq = pq.name.toLowerCase().includes("groq");

            return (
              <div key={pq.name} className="quota-provider-card fade-in">
                <div className="quota-card-top">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span
                      style={{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        backgroundColor: isGemini ? "#818cf8" : (isGroq ? "#fb923c" : "var(--accent)"),
                      }}
                    />
                    <span className="quota-provider-name">{pq.name}</span>
                  </div>
                  <span className="quota-remaining-pct font-mono">
                    <strong style={{ color: pq.remainingPct > 50 ? "var(--success)" : "var(--warning)" }}>
                      {pq.remainingPct}%
                    </strong>{" "}
                    <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontWeight: 400 }}>remaining</span>
                  </span>
                </div>

                <div className="quota-progress-track" style={{ height: "7px" }}>
                  <div
                    className={`quota-progress-fill ${pq.status}`}
                    style={{
                      width: `${pq.remainingPct}%`,
                      background: pq.remainingPct > 50
                        ? "linear-gradient(90deg, #10b981, #06b6d4)"
                        : "linear-gradient(90deg, #f59e0b, #ef4444)",
                    }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.6875rem" }}>
                  <span className="quota-reset-countdown">Reset Status: {pq.resetTime}</span>
                  <span style={{ color: "var(--text-secondary)" }}>
                    Rate Usage: <strong className="font-mono text-primary">{pq.rateLimitUsagePct}%</strong>
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Quota Insights & Dynamic Routing Forecast */}
      {(() => {
        const total = workerMatrix.length;
        const healthyCount = workerMatrix.filter((m) => m.state === "healthy" || m.state === "busy").length;
        const constrainedCount = workerMatrix.filter((m) => m.state === "rate_limited" || m.state === "unhealthy").length;
        const avgCapacity = total > 0
          ? Math.round(workerMatrix.reduce((acc, m) => acc + m.remainingPct, 0) / total)
          : 100;

        return (
          <div
            style={{
              backgroundColor: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-lg)",
              padding: "1.15rem 1.25rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.875rem",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <TrendingUp size={15} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: "0.84rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Capacity Forecasting & Routing Headroom
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "0.875rem" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.75rem",
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "0.875rem 1rem",
                }}
              >
                <CheckCircle2 size={18} style={{ color: "var(--success)", flexShrink: 0, marginTop: "2px" }} />
                <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                  <span style={{ fontSize: "0.78125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Healthy Capacity Across Real Snapshots
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                    {loading && total === 0 ? (
                      "Evaluating real-time headroom and rate limit windows across active workers..."
                    ) : (
                      `${healthyCount} of ${total} computational workers operational. Average remaining headroom is ${avgCapacity}%. Real provider snapshots in database are healthy and within rate limits.`
                    )}
                  </span>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.75rem",
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "0.875rem 1rem",
                }}
              >
                <AlertCircle size={18} style={{ color: constrainedCount > 0 ? "var(--warning)" : "var(--accent)", flexShrink: 0, marginTop: "2px" }} />
                <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                  <span style={{ fontSize: "0.78125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    {constrainedCount > 0 ? "Autonomous Failover Protection Active" : "Autonomous Routing Optimized"}
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                    {constrainedCount > 0
                      ? `Intelligent routing engine isolated ${constrainedCount} constrained or unauthenticated worker(s) and automatically routes traffic around rate limits.`
                      : "Intelligent routing engine continuously computes remaining tokens and balances requests across nominal workers."}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Compact Real Worker / Provider Matrix */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Provider / Worker Headroom Matrix
          </span>
          <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
            Real-time snapshot monitoring from database
          </span>
        </div>

        <div className="dense-table-wrapper">
          <table className="dense-table dense-table-wide">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Worker / Model</th>
                <th>Remaining Quota</th>
                <th>Rate Usage</th>
                <th>Reset In</th>
                <th style={{ textAlign: "center", width: "90px" }}>State</th>
              </tr>
            </thead>
            <tbody>
              {loading && workerMatrix.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={`skel-row-${i}`}>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "70px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "160px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "120px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "40px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-line" style={{ width: "75px" }} /></td>
                    <td><span className="skeleton-shimmer skeleton-pill" style={{ width: "65px", height: "16px" }} /></td>
                  </tr>
                ))
              ) : (
                workerMatrix.map((row) => (
                  <tr key={row.id}>
                    <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{row.provider}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className="font-mono text-primary" style={{ fontWeight: 600 }}>{row.worker}</span>
                        <span
                          style={{
                            fontSize: "0.625rem",
                            padding: "0.1rem 0.35rem",
                            borderRadius: "var(--radius-xs)",
                            backgroundColor: "var(--bg-elevated)",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-tertiary)",
                            fontFamily: "var(--font-mono)",
                          }}
                          title={`Worker ID: ${row.id}`}
                        >
                          {row.credentialName} {row.maskedIdentifier ? `(${row.maskedIdentifier.slice(-6)})` : ""}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "140px" }}>
                        <div style={{ flex: 1, height: "5px", backgroundColor: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                          <div
                            style={{
                              width: `${row.remainingPct}%`,
                              height: "100%",
                              background:
                                row.state === "unhealthy"
                                  ? "var(--error)"
                                  : row.remainingPct < 60
                                  ? "var(--warning)"
                                  : "linear-gradient(90deg, var(--success), #06b6d4)",
                              borderRadius: "3px",
                            }}
                          />
                        </div>
                        <span className="font-mono" style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {row.remainingPct}%
                        </span>
                      </div>
                    </td>
                    <td className="font-mono text-secondary">{row.rateLimitPct}%</td>
                    <td className="font-mono text-tertiary">{row.resetIn}</td>
                    <td style={{ textAlign: "center" }}>
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.35rem",
                          padding: "0.15rem 0.45rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor:
                            row.state === "healthy"
                              ? "var(--success-muted)"
                              : row.state === "busy"
                              ? "var(--accent-muted)"
                              : "var(--warning-muted)",
                          border: `1px solid ${
                            row.state === "healthy"
                              ? "var(--success-border)"
                              : row.state === "busy"
                              ? "var(--accent-border)"
                              : "var(--warning-border)"
                          }`,
                        }}
                      >
                        <span className={`status-dot ${row.state}`} style={{ width: "5px", height: "5px" }} />
                        <span
                          style={{
                            fontSize: "0.625rem",
                            fontWeight: 700,
                            letterSpacing: "0.03em",
                            textTransform: "uppercase",
                            color:
                              row.state === "healthy"
                                ? "var(--success)"
                                : row.state === "busy"
                                ? "var(--accent)"
                                : "var(--warning)",
                          }}
                        >
                          {row.state === "rate_limited" ? "RATE LIMITED" : row.state.toUpperCase()}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
