import { useState, useEffect, useCallback } from "react";
import { LogOut, Sun, Moon, Server, Cpu, Layers, Clock } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";
import { apiClient } from "../../lib/apiClient";

export function Topbar() {
  const { logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [metrics, setMetrics] = useState<{
    workersCount: number | null;
    providersCount: number | null;
    totalRequests: number | null;
    p50LatencyMs: number | null;
  }>({
    workersCount: null,
    providersCount: null,
    totalRequests: null,
    p50LatencyMs: null,
  });

  const fetchLiveMetrics = useCallback(async () => {
    try {
      const data = await apiClient.get("/api/metrics/topbar");
      if (data) {
        setMetrics({
          workersCount: data.workers_count ?? 0,
          providersCount: data.providers_count ?? 0,
          totalRequests: data.total_requests ?? 0,
          p50LatencyMs: data.p50_latency_ms ?? 0,
        });
      }
    } catch {
      // Keep existing
    }
  }, []);

  useEffect(() => {
    fetchLiveMetrics();
    const metricInterval = setInterval(fetchLiveMetrics, 10000);
    return () => clearInterval(metricInterval);
  }, [fetchLiveMetrics]);

  const formatLatency = (ms: number | null) => {
    if (ms == null) return null;
    return ms > 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
  };

  return (
    <header className="enterprise-topbar">
      {/* Left: Operational Health & Live Metrics */}
      <div className="topbar-left-cluster">
        {/* Gateway Health Indicator */}
        <div className="topbar-health-chip" title="Gateway Engine healthy & operational">
          <span className="health-pulse-dot">
            <span className="health-pulse-ring" />
          </span>
          <span className="health-label">OPERATIONAL</span>
        </div>

        <div className="topbar-divider" />

        {/* Live Metrics Chips */}
        <div className="topbar-metrics-strip">
          <div className="topbar-metric-chip" title="Active computational workers registered">
            <Server size={12} className="topbar-metric-icon" />
            <span className="topbar-metric-value">
              {metrics.workersCount !== null ? (
                metrics.workersCount
              ) : (
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "16px", height: "12px", display: "inline-block" }} />
              )}
            </span>
            <span className="topbar-metric-label">workers</span>
          </div>

          <div className="topbar-metric-chip" title="Connected AI model providers">
            <Cpu size={12} className="topbar-metric-icon" />
            <span className="topbar-metric-value">
              {metrics.providersCount !== null ? (
                metrics.providersCount
              ) : (
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "14px", height: "12px", display: "inline-block" }} />
              )}
            </span>
            <span className="topbar-metric-label">providers</span>
          </div>

          <div className="topbar-metric-chip" title="Total requests routed through gateway">
            <Layers size={12} className="topbar-metric-icon" />
            <span className="topbar-metric-value">
              {metrics.totalRequests !== null ? (
                metrics.totalRequests
              ) : (
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "20px", height: "12px", display: "inline-block" }} />
              )}
            </span>
            <span className="topbar-metric-label">requests</span>
          </div>

          <div className="topbar-metric-chip" title="50th percentile execution latency">
            <Clock size={12} className="topbar-metric-icon" />
            <span className="topbar-metric-value">
              {metrics.p50LatencyMs !== null ? (
                formatLatency(metrics.p50LatencyMs)
              ) : (
                <span className="skeleton-shimmer skeleton-pill" style={{ width: "28px", height: "12px", display: "inline-block" }} />
              )}
            </span>
            <span className="topbar-metric-label">avg latency</span>
          </div>
        </div>
      </div>

      {/* Right: Version, Theme Switcher, Sign out */}
      <div className="topbar-right-cluster">
        <div className="topbar-version-pill">
          <span>v1.0.0</span>
        </div>

        <div className="topbar-divider" />

        {/* Theme Toggle */}
        <button
          className="topbar-icon-btn"
          onClick={toggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          aria-label="Toggle color theme"
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        <div className="topbar-divider" />

        {/* Logout */}
        <button
          className="topbar-icon-btn danger-hover"
          onClick={logout}
          title="Sign out of WRAP"
          aria-label="Sign out"
        >
          <LogOut size={15} />
        </button>
      </div>
    </header>
  );
}

