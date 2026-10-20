import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, RefreshCw, Server, Cpu, ShieldCheck, Layers, ExternalLink, ArrowRight } from "lucide-react";
import { motion } from "motion/react";
import { apiClient } from "../lib/apiClient";

interface ParticipatingTier {
  id: string;
  name: string;
  priorityRank: number;
  totalInCascade: number;
  strategy: string;
}

interface WorkerItem {
  id: string;
  name: string;
  provider: string;
  model: string;
  qps: number;
  p50Ms: number;
  quotaRemainingPct: number | null;
  loadPct: number;
  status: "healthy" | "busy" | "rate_limited" | "degraded" | "unhealthy" | "offline";
  credentialName: string;
  relatedModels: string[];
  participatingTiers: ParticipatingTier[];
}

interface ModelGroupItem {
  id: string;
  name: string;
  description?: string;
  routing_strategy?: string;
  models: string[];
  active_workers_count?: number;
}

function getStatusBadgeInfo(status: string) {
  switch (status) {
    case "healthy":
      return {
        bg: "var(--success-muted)",
        color: "var(--success)",
        label: "HEALTHY",
      };
    case "busy":
      return {
        bg: "var(--accent-muted)",
        color: "var(--accent)",
        label: "BUSY",
      };
    case "rate_limited":
      return {
        bg: "var(--warning-muted)",
        color: "var(--warning)",
        label: "RATE LIMITED",
      };
    case "degraded":
      return {
        bg: "var(--warning-muted)",
        color: "var(--warning)",
        label: "DEGRADED",
      };
    case "unhealthy":
    case "failed":
      return {
        bg: "var(--error-muted)",
        color: "var(--error)",
        label: "UNHEALTHY",
      };
    case "offline":
    default:
      return {
        bg: "var(--bg-elevated)",
        color: "var(--text-tertiary)",
        label: "OFFLINE",
      };
  }
}

function getWorkerTierParticipation(
  workerModel: string,
  workerProvider: string,
  groups: ModelGroupItem[]
): ParticipatingTier[] {
  const normWorker = (workerModel || "").toLowerCase().trim();
  const normProv = (workerProvider || "").toLowerCase().trim();
  const fullWorker = normWorker.includes("/") ? normWorker : `${normProv}/${normWorker}`;
  const bareWorker = normWorker.split("/").pop() || normWorker;

  const result: ParticipatingTier[] = [];

  for (const group of groups) {
    if (!group.models || !Array.isArray(group.models)) continue;
    for (let i = 0; i < group.models.length; i++) {
      const gm = (group.models[i] || "").toLowerCase().trim();
      const gmBare = gm.split("/").pop() || gm;
      if (gm === fullWorker || gm === normWorker || gmBare === bareWorker) {
        result.push({
          id: group.id,
          name: group.name,
          priorityRank: i + 1,
          totalInCascade: group.models.length,
          strategy: group.routing_strategy || "priority_fallback",
        });
        break;
      }
    }
  }

  return result;
}

function getInitialWorkers(): WorkerItem[] {
  try {
    const raw = sessionStorage.getItem("wrap_cached_workers");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function getInitialModelGroups(): ModelGroupItem[] {
  try {
    const raw = sessionStorage.getItem("wrap_cached_model_groups");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

let cachedWorkers: WorkerItem[] = getInitialWorkers();
let cachedModelGroups: ModelGroupItem[] = getInitialModelGroups();

export function Workers() {
  const navigate = useNavigate();
  const [workers, setWorkers] = useState<WorkerItem[]>(cachedWorkers);
  const [modelGroups, setModelGroups] = useState<ModelGroupItem[]>(cachedModelGroups);
  const [loading, setLoading] = useState(cachedWorkers.length === 0);
  const [searchQuery, setSearchQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState<string>("ALL");
  const [tierFilter, setTierFilter] = useState<string>("ALL");
  const [selectedWorker, setSelectedWorker] = useState<WorkerItem | null>(cachedWorkers[0] || null);
  const [checkingHealth, setCheckingHealth] = useState(false);

  const mapWorkerItems = useCallback((
    rawList: any[],
    credMap: Map<string, string>,
    modelsByProvider: Map<string, string[]>,
    groups: ModelGroupItem[]
  ): WorkerItem[] => {
    return rawList.map((w: any, idx: number) => {
      const providerKey = (w.provider || "groq").toLowerCase();
      const pName = w.provider ? (w.provider.charAt(0).toUpperCase() + w.provider.slice(1)) : "Groq";
      const catalog = modelsByProvider.get(providerKey) || [w.model];
      const credDesc = w.credential_name
        ? `${w.credential_name} (${w.masked_identifier || w.provider})`
        : (credMap.get(w.credential_id) || `${w.provider}_key (${w.provider})`);

      const qpsVal = w.requests_per_second != null ? Number(w.requests_per_second) : (w.total_requests ? Number((w.total_requests / 60).toFixed(2)) : 0);
      const p50Val = w.p50_latency_ms != null ? Number(w.p50_latency_ms) : 0;
      const quotaVal = w.quota_remaining_pct != null
        ? Number(w.quota_remaining_pct)
        : (w.enabled ? (w.health_status === "healthy" ? 100 : 0) : null);
      const loadVal = w.load_pct != null
        ? Number(w.load_pct)
        : (w.active_requests ? Math.min(100, w.active_requests * 50) : 0);

      let statusVal: "healthy" | "busy" | "rate_limited" | "degraded" | "unhealthy" | "offline" = "offline";
      if (!w.enabled) {
        statusVal = "offline";
      } else if ((w.active_requests != null && w.active_requests > 0) || (w.load_pct != null && w.load_pct > 0)) {
        statusVal = "busy";
      } else if (w.health_status === "rate_limited" || (quotaVal === 0 && w.health_status !== "unhealthy" && w.enabled)) {
        statusVal = "rate_limited";
      } else if (w.health_status === "unhealthy") {
        statusVal = "unhealthy";
      } else if (w.health_status === "degraded") {
        statusVal = "degraded";
      } else if (w.health_status === "healthy") {
        statusVal = "healthy";
      } else {
        statusVal = "healthy";
      }

      const participatingTiers = getWorkerTierParticipation(w.model, pName, groups);

      return {
        id: w.id || `worker-${idx}`,
        name: w.name || w.model || `worker-${w.id?.slice(0, 6)}`,
        provider: pName,
        model: w.model || "unknown",
        qps: qpsVal,
        p50Ms: p50Val,
        quotaRemainingPct: quotaVal,
        loadPct: loadVal,
        status: statusVal,
        credentialName: credDesc,
        relatedModels: catalog.slice(0, 8),
        participatingTiers,
      };
    });
  }, []);

  const fetchWorkers = useCallback(async (isManualRefresh = false) => {
    if (cachedWorkers.length === 0 || isManualRefresh) {
      setLoading(true);
    }
    try {
      const wkPromise = apiClient.get("/api/workers", { bypassCache: isManualRefresh });
      const credPromise = apiClient.get("/api/credentials", { bypassCache: isManualRefresh });
      const modPromise = apiClient.get("/api/provider-models", { bypassCache: isManualRefresh });
      const mgPromise = apiClient.get("/api/model-groups", { bypassCache: isManualRefresh });

      // Immediate first pass: As soon as workers resolve, render them immediately!
      wkPromise.then((rawWorkers) => {
        if (Array.isArray(rawWorkers) && rawWorkers.length > 0) {
          const quickMapped = mapWorkerItems(rawWorkers, new Map(), new Map(), cachedModelGroups);
          setWorkers(quickMapped);
          cachedWorkers = quickMapped;
          setLoading(false); // Unblock display in ~15ms!
          setSelectedWorker((prev) => prev || quickMapped[0] || null);
        }
      }).catch((e) => console.error("Quick workers load error:", e));

      const [wkRes, credRes, modRes, mgRes] = await Promise.allSettled([
        wkPromise,
        credPromise,
        modPromise,
        mgPromise,
      ]);

      const credMap = new Map<string, string>();
      if (credRes.status === "fulfilled" && Array.isArray(credRes.value)) {
        for (const c of credRes.value) {
          credMap.set(c.id, `${c.name} (${c.masked_identifier || c.provider})`);
        }
      }

      const modelsByProvider = new Map<string, string[]>();
      if (modRes.status === "fulfilled" && Array.isArray(modRes.value)) {
        for (const m of modRes.value) {
          const prov = (m.provider || "default").toLowerCase();
          const existing = modelsByProvider.get(prov) || [];
          existing.push(m.external_model_id);
          modelsByProvider.set(prov, existing);
        }
      }

      const groups: ModelGroupItem[] = (mgRes.status === "fulfilled" && Array.isArray(mgRes.value))
        ? mgRes.value
        : [];
      cachedModelGroups = groups;
      setModelGroups(groups);

      if (wkRes.status === "fulfilled" && Array.isArray(wkRes.value)) {
        const mapped = mapWorkerItems(wkRes.value, credMap, modelsByProvider, groups);
        cachedWorkers = mapped;
        setWorkers(mapped);
        try {
          sessionStorage.setItem("wrap_cached_workers", JSON.stringify(mapped));
          sessionStorage.setItem("wrap_cached_model_groups", JSON.stringify(groups));
        } catch {}
        setSelectedWorker((prev) => {
          if (!prev && mapped.length > 0) return mapped[0];
          if (prev) {
            const updated = mapped.find((item) => item.id === prev.id);
            return updated || (mapped.length > 0 ? mapped[0] : null);
          }
          return null;
        });
      }
    } catch (e) {
      console.error("Failed to load workers:", e);
    } finally {
      setLoading(false);
    }
  }, [mapWorkerItems]);

  const handleHealthSweep = async () => {
    setCheckingHealth(true);
    try {
      await apiClient.post("/api/workers/health-check");
      await fetchWorkers(true);
    } catch (e) {
      console.error("Health check sweep failed:", e);
    } finally {
      setCheckingHealth(false);
    }
  };

  useEffect(() => {
    fetchWorkers();
    const interval = setInterval(fetchWorkers, 10000);
    return () => clearInterval(interval);
  }, [fetchWorkers]);

  const providers = useMemo(() => {
    const set = new Set<string>(["ALL"]);
    for (const w of workers) {
      if (w.provider) set.add(w.provider);
    }
    return Array.from(set);
  }, [workers]);

  const filteredWorkers = useMemo(() => {
    return workers.filter((w) => {
      if (providerFilter !== "ALL" && w.provider.toLowerCase() !== providerFilter.toLowerCase()) return false;
      if (tierFilter !== "ALL" && !w.participatingTiers.some((t) => t.id === tierFilter)) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchesTier = w.participatingTiers.some((t) => t.name.toLowerCase().includes(q));
        return (
          w.name.toLowerCase().includes(q) ||
          w.provider.toLowerCase().includes(q) ||
          w.model.toLowerCase().includes(q) ||
          matchesTier
        );
      }
      return true;
    });
  }, [workers, providerFilter, tierFilter, searchQuery]);

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <Server size={18} style={{ color: "var(--accent)" }} />
            <span>Active Computational Workers</span>
          </h1>
          <p className="page-subtitle">
            Infrastructure capacity, real-time load distribution, credential mapping, and virtual tier cascade membership
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleHealthSweep}
            disabled={checkingHealth || loading}
            title="Probe all active worker endpoints and refresh health statuses"
          >
            <ShieldCheck size={12} className={checkingHealth ? "animate-spin" : ""} style={{ color: "var(--success)" }} />
            <span>{checkingHealth ? "Probing Providers..." : "Probe Health"}</span>
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => fetchWorkers(true)} disabled={loading} title="Refresh workers">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Filter toolbar */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem", marginBottom: "1rem" }}>
        <div className="table-toolbar" style={{ margin: 0 }}>
          <div className="search-input-wrap">
            <Search size={14} />
            <input
              type="text"
              className="search-input"
              placeholder="Search workers, models, or virtual tiers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="filter-btn-group">
            {providers.map((p) => (
              <button
                key={p}
                className={`filter-btn ${providerFilter === p ? "active" : ""}`}
                onClick={() => setProviderFilter(p)}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Virtual Tiers Filter Ribbon */}
        {modelGroups.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              flexWrap: "wrap",
              padding: "0.45rem 0.75rem",
              backgroundColor: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <span
              style={{
                fontSize: "0.6875rem",
                fontWeight: 600,
                color: "var(--text-tertiary)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                display: "flex",
                alignItems: "center",
                gap: "0.35rem",
              }}
            >
              <Layers size={12} style={{ color: "var(--accent)" }} />
              <span>Virtual Tier:</span>
            </span>
            <button
              className={`filter-btn ${tierFilter === "ALL" ? "active" : ""}`}
              onClick={() => setTierFilter("ALL")}
              style={{ fontSize: "0.6875rem", padding: "0.2rem 0.5rem" }}
            >
              ALL TIERS
            </button>
            {modelGroups.map((g) => {
              const count = workers.filter((w) => w.participatingTiers.some((t) => t.id === g.id)).length;
              return (
                <button
                  key={g.id}
                  className={`filter-btn ${tierFilter === g.id ? "active" : ""}`}
                  onClick={() => setTierFilter(g.id)}
                  style={{
                    fontSize: "0.6875rem",
                    padding: "0.2rem 0.55rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.35rem",
                  }}
                >
                  <span>{g.name}</span>
                  <span className="font-mono" style={{ fontSize: "0.625rem", opacity: 0.75 }}>
                    ({count})
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Main Content Layout: Two-pane Operational Split View */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: "1rem", alignItems: "start" }}>
        {/* Left: Real Workers List */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {loading && workers.length === 0 ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div
                key={`skel-w-${i}`}
                style={{
                  backgroundColor: "var(--bg-surface)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "0.75rem 1rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="skeleton-shimmer skeleton-pill" style={{ width: "8px", height: "8px", borderRadius: "50%" }} />
                    <span className="skeleton-shimmer skeleton-line" style={{ width: "140px" }} />
                  </div>
                  <span className="skeleton-shimmer skeleton-pill" style={{ width: "55px", height: "14px" }} />
                </div>
                <div style={{ display: "flex", gap: "1rem" }}>
                  <span className="skeleton-shimmer skeleton-line" style={{ width: "70px" }} />
                  <span className="skeleton-shimmer skeleton-line" style={{ width: "70px" }} />
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <span className="skeleton-shimmer skeleton-pill" style={{ width: "100px", height: "18px" }} />
                </div>
              </div>
            ))
          ) : filteredWorkers.length === 0 ? (
            <div
              style={{
                backgroundColor: "var(--bg-surface)",
                border: "1px dashed var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "2.5rem 1rem",
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <Server size={24} style={{ color: "var(--text-tertiary)" }} />
              <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-secondary)" }}>
                No active workers match this filter
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                Try selecting &quot;ALL TIERS&quot; or clearing your search term.
              </span>
            </div>
          ) : (
            filteredWorkers.map((w) => {
              const isSelected = selectedWorker?.id === w.id;
              const bInfo = getStatusBadgeInfo(w.status);
              const isGemini = w.provider.toLowerCase().includes("gemini");
              const isGroq = w.provider.toLowerCase().includes("groq");

              return (
                <div
                  key={w.id}
                  onClick={() => setSelectedWorker(w)}
                  style={{
                    backgroundColor: isSelected ? "var(--bg-elevated)" : "var(--bg-surface)",
                    border: isSelected ? "1px solid var(--accent)" : "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-md)",
                    padding: "0.875rem 1rem",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.55rem",
                    boxShadow: isSelected ? "0 0 0 1px var(--accent), 0 4px 16px -2px rgba(59, 130, 246, 0.2)" : "var(--shadow-card)",
                    transition: "all 0.15s cubic-bezier(0.16, 1, 0.3, 1)",
                    transform: isSelected ? "translateX(2px)" : "none",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span className={`status-dot ${w.status}`} />
                      <span className="font-mono text-primary" style={{ fontWeight: 600, fontSize: "0.84rem" }}>
                        {w.model}
                      </span>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          fontWeight: 500,
                          color: isGemini ? "#818cf8" : (isGroq ? "#fb923c" : "var(--text-tertiary)"),
                          backgroundColor: isGemini ? "rgba(99, 102, 241, 0.08)" : (isGroq ? "rgba(249, 115, 22, 0.08)" : "var(--bg-elevated)"),
                          padding: "0.1rem 0.35rem",
                          borderRadius: "var(--radius-xs)",
                          border: `1px solid ${isGemini ? "rgba(99, 102, 241, 0.2)" : (isGroq ? "rgba(249, 115, 22, 0.2)" : "var(--border-subtle)")}`,
                        }}
                      >
                        {w.provider}
                      </span>
                    </div>
                    <span
                      style={{
                        fontSize: "0.625rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        padding: "0.15rem 0.5rem",
                        borderRadius: "9999px",
                        backgroundColor: bInfo.bg,
                        color: bInfo.color,
                        letterSpacing: "0.03em",
                      }}
                    >
                      {bInfo.label}
                    </span>
                  </div>

                  {/* Worker Metrics Row */}
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", fontSize: "0.6875rem", color: "var(--text-secondary)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                      <span>
                        Throughput: <strong className="font-mono text-primary">{w.qps.toFixed(1)} req/s</strong>
                      </span>
                      <span>
                        p50: <strong className="font-mono text-primary">{w.p50Ms}ms</strong>
                      </span>
                      <span>
                        Headroom:{" "}
                        {w.status === "offline" || w.quotaRemainingPct == null ? (
                          <span className="font-mono text-secondary" style={{ fontSize: "0.75rem" }}>N/A (Disabled)</span>
                        ) : (
                          <strong className="font-mono" style={{ color: w.quotaRemainingPct > 30 ? "var(--success)" : "var(--warning)" }}>
                            {w.quotaRemainingPct}%
                          </strong>
                        )}
                      </span>
                    </div>

                    {/* Micro load bar */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "130px" }}>
                      <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>Load</span>
                      <div style={{ flex: 1, height: "6px", backgroundColor: "var(--bg-subtle)", borderRadius: "3px", overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${w.loadPct}%`,
                            height: "100%",
                            background: w.loadPct > 80 ? "var(--warning)" : "linear-gradient(90deg, var(--accent), #38bdf8)",
                            borderRadius: "3px",
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>
                      <span className="font-mono text-primary" style={{ fontSize: "0.65rem", fontWeight: 600 }}>{w.loadPct}%</span>
                    </div>
                  </div>

                  {/* Participating Virtual Tiers Badge Row */}
                  {w.participatingTiers.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "0.35rem",
                        paddingTop: "0.45rem",
                        borderTop: "1px solid var(--border-subtle)",
                      }}
                    >
                      <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", display: "flex", alignItems: "center", gap: "0.25rem", fontWeight: 600 }}>
                        <Layers size={11} style={{ color: "var(--accent)" }} />
                        <span>Cascades:</span>
                      </span>
                      {w.participatingTiers.map((t) => (
                        <span
                          key={t.id}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            fontSize: "0.625rem",
                            padding: "0.12rem 0.45rem",
                            borderRadius: "var(--radius-xs)",
                            backgroundColor: t.priorityRank === 1 ? "var(--accent-muted)" : "var(--bg-elevated)",
                            color: t.priorityRank === 1 ? "var(--accent)" : "var(--text-secondary)",
                            border: t.priorityRank === 1 ? "1px solid var(--accent-border)" : "1px solid var(--border-subtle)",
                            fontWeight: 500,
                          }}
                          title={`${t.name}: Priority #${t.priorityRank} in cascade (${t.strategy})`}
                        >
                          <span>{t.name}</span>
                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.5625rem",
                              fontWeight: 700,
                              padding: "0 0.25rem",
                              borderRadius: "2px",
                              backgroundColor: t.priorityRank === 1 ? "var(--accent)" : "var(--bg-subtle)",
                              color: t.priorityRank === 1 ? "var(--bg-canvas)" : "var(--text-primary)",
                            }}
                          >
                            #{t.priorityRank}
                          </span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Right: Worker Details & Resource Relationship Inspector */}
        {loading && !selectedWorker ? (
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
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span className="skeleton-shimmer skeleton-line" style={{ width: "140px" }} />
              <span className="skeleton-shimmer skeleton-pill" style={{ width: "65px", height: "16px" }} />
            </div>
            <div className="info-grid">
              <span className="skeleton-shimmer skeleton-line" style={{ width: "100%", height: "20px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "100%", height: "20px" }} />
            </div>
            <span className="skeleton-shimmer skeleton-line" style={{ width: "100%", height: "60px", borderRadius: "var(--radius-sm)" }} />
          </div>
        ) : selectedWorker && (
          <motion.div
            key={selectedWorker.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Cpu size={15} style={{ color: "var(--accent)" }} />
                <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                  {selectedWorker.model}
                </span>
              </div>
              <span className={`status-pill ${selectedWorker.status}`}>
                <span className="status-pulse" />
                {getStatusBadgeInfo(selectedWorker.status).label}
              </span>
            </div>

            {/* Performance Stats */}
            <div className="info-grid">
              <div className="info-row">
                <span className="info-label">Provider</span>
                <span className="info-val">{selectedWorker.provider}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Current Model</span>
                <span className="info-val font-mono">{selectedWorker.model}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Execution Load</span>
                <span className="info-val font-mono">{selectedWorker.loadPct}%</span>
              </div>
              <div className="info-row">
                <span className="info-label">Remaining Quota</span>
                <span className="info-val font-mono">
                  {selectedWorker.status === "offline" || selectedWorker.quotaRemainingPct == null
                    ? "N/A (Disabled)"
                    : `${selectedWorker.quotaRemainingPct}%`}
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">p50 Latency</span>
                <span className="info-val font-mono">{selectedWorker.p50Ms}ms</span>
              </div>
              <div className="info-row">
                <span className="info-label">Throughput</span>
                <span className="info-val font-mono">{selectedWorker.qps.toFixed(1)} req/s</span>
              </div>
            </div>

            {/* RESOURCE RELATIONSHIP MODEL */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.6875rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-tertiary)" }}>
                  Resource Relationship Model
                </span>
                <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                  1 Credential → {selectedWorker.relatedModels.length} Discovered Models
                </span>
              </div>

              {/* Credential Master Card */}
              <div
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  border: "1px solid var(--border-default)",
                  borderRadius: "var(--radius-md)",
                  padding: "0.75rem 0.875rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
                  <div
                    style={{
                      width: "28px",
                      height: "28px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "var(--accent-muted)",
                      border: "1px solid var(--accent-border)",
                      color: "var(--accent)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ShieldCheck size={15} />
                  </div>
                  <div>
                    <div style={{ fontSize: "0.78125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      {selectedWorker.credentialName}
                    </div>
                    <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      Provider: {selectedWorker.provider.toUpperCase()} (Encrypted & Verified)
                    </div>
                  </div>
                </div>
                <span
                  style={{
                    fontSize: "0.625rem",
                    fontWeight: 700,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    padding: "0.15rem 0.45rem",
                    borderRadius: "9999px",
                    backgroundColor: "var(--success-muted)",
                    color: "var(--success)",
                    border: "1px solid var(--success-border)",
                  }}
                >
                  AUTHENTICATED
                </span>
              </div>

              {/* Discovered Model Cards Canvas */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.4rem",
                  paddingLeft: "0.5rem",
                  borderLeft: "2px solid var(--border-subtle)",
                  marginLeft: "0.875rem",
                }}
              >
                {selectedWorker.relatedModels.map((m) => {
                  const isCurrent = m === selectedWorker.model;
                  const isReasoning = m.includes("3.") || m.includes("pro") || m.includes("27b");
                  const isVision = m.includes("flash") || m.includes("vl") || m.includes("4o");

                  return (
                    <div
                      key={m}
                      style={{
                        backgroundColor: isCurrent ? "var(--bg-elevated)" : "var(--bg-surface)",
                        border: isCurrent ? "1px solid var(--accent)" : "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        padding: "0.5rem 0.75rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "0.5rem",
                        boxShadow: isCurrent ? "0 0 12px -2px rgba(59, 130, 246, 0.2)" : "none",
                        transition: "all 0.12s ease",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", minWidth: 0 }}>
                        <span className={`status-dot ${isCurrent ? "healthy" : "offline"}`} style={{ width: "5px", height: "5px" }} />
                        <span
                          className="font-mono text-primary"
                          style={{
                            fontWeight: isCurrent ? 600 : 500,
                            fontSize: "0.75rem",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {m}
                        </span>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexShrink: 0 }}>
                        {isCurrent ? (
                          <span
                            style={{
                              fontSize: "0.625rem",
                              fontWeight: 700,
                              color: "var(--accent)",
                              backgroundColor: "var(--accent-muted)",
                              border: "1px solid var(--accent-border)",
                              padding: "0.1rem 0.4rem",
                              borderRadius: "var(--radius-xs)",
                              letterSpacing: "0.03em",
                            }}
                          >
                            ACTIVE ROUTE
                          </span>
                        ) : (
                          <>
                            {isReasoning && (
                              <span style={{ fontSize: "0.5625rem", color: "var(--text-tertiary)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", padding: "0.05rem 0.3rem", borderRadius: "2px" }}>
                                Reasoning
                              </span>
                            )}
                            {isVision && (
                              <span style={{ fontSize: "0.5625rem", color: "var(--text-tertiary)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", padding: "0.05rem 0.3rem", borderRadius: "2px" }}>
                                Vision
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* VIRTUAL TIER CASCADE MEMBERSHIP */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span
                  style={{
                    fontSize: "0.6875rem",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: "var(--text-tertiary)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                  }}
                >
                  <Layers size={12} style={{ color: "var(--accent)" }} />
                  <span>Virtual Tier Cascade Membership</span>
                </span>
                <button
                  onClick={() => navigate("/settings/model-groups")}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--accent)",
                    fontSize: "0.625rem",
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                    padding: 0,
                  }}
                >
                  <span>Manage Tiers</span>
                  <ExternalLink size={10} />
                </button>
              </div>

              {selectedWorker.participatingTiers.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {selectedWorker.participatingTiers.map((t) => (
                    <div
                      key={t.id}
                      style={{
                        backgroundColor: "var(--bg-elevated)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        padding: "0.625rem 0.75rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.4rem",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <span style={{ fontWeight: 600, fontSize: "0.75rem", color: "var(--text-primary)" }}>
                            {t.name}
                          </span>
                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.625rem",
                              padding: "0.05rem 0.35rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--bg-subtle)",
                              color: "var(--text-tertiary)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            {t.strategy}
                          </span>
                        </div>
                        <span
                          className="font-mono"
                          style={{
                            fontSize: "0.6875rem",
                            fontWeight: 600,
                            padding: "0.1rem 0.45rem",
                            borderRadius: "var(--radius-xs)",
                            backgroundColor: t.priorityRank === 1 ? "var(--success-muted)" : "var(--warning-muted)",
                            color: t.priorityRank === 1 ? "var(--success)" : "var(--warning)",
                            border: t.priorityRank === 1 ? "1px solid var(--success-border)" : "1px solid var(--warning-border)",
                          }}
                        >
                          {t.priorityRank === 1 ? `Primary (Rank 1/${t.totalInCascade})` : `Fallback (Step ${t.priorityRank}/${t.totalInCascade})`}
                        </span>
                      </div>

                      {/* Visual Cascade Stepper */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.3rem",
                          fontSize: "0.625rem",
                          color: "var(--text-secondary)",
                          marginTop: "0.15rem",
                        }}
                      >
                        <span style={{ color: "var(--text-tertiary)" }}>Cascade chain:</span>
                        {Array.from({ length: t.totalInCascade }).map((_, stepIdx) => {
                          const isCurrentStep = stepIdx + 1 === t.priorityRank;
                          return (
                            <React.Fragment key={stepIdx}>
                              <span
                                className="font-mono"
                                style={{
                                  padding: "0.1rem 0.35rem",
                                  borderRadius: "var(--radius-xs)",
                                  fontSize: "0.5625rem",
                                  fontWeight: isCurrentStep ? 700 : 400,
                                  backgroundColor: isCurrentStep ? "var(--accent)" : "var(--bg-subtle)",
                                  color: isCurrentStep ? "var(--bg-canvas)" : "var(--text-tertiary)",
                                  border: isCurrentStep ? "none" : "1px solid var(--border-subtle)",
                                }}
                              >
                                Step {stepIdx + 1}
                              </span>
                              {stepIdx < t.totalInCascade - 1 && (
                                <ArrowRight size={10} style={{ color: "var(--text-muted)" }} />
                              )}
                            </React.Fragment>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    backgroundColor: "var(--bg-elevated)",
                    border: "1px dashed var(--border-subtle)",
                    borderRadius: "var(--radius-sm)",
                    padding: "0.75rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.35rem",
                  }}
                >
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                    Direct-routed Worker
                  </span>
                  <p style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", margin: 0, lineHeight: 1.4 }}>
                    This worker is reachable via explicit model parameter (<code className="font-mono">{selectedWorker.model}</code>).
                    To participate in automated multi-provider failover, add it to a Virtual Tier.
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
