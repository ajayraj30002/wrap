import React, { useState, useMemo } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import { motion, AnimatePresence } from "motion/react";
import {
  DollarSign,
  PiggyBank,
  ShieldAlert,
  RotateCcw,
  Sliders,
  Activity,
  Check,
  X,
  RefreshCw,
  Search,
  ChevronDown,
  ChevronUp,
  Clock,
  Sparkles,
  Info,
  ArrowUpDown,
  KeyRound,
  Cpu,
} from "lucide-react";
import { apiClient } from "../../lib/apiClient";
import { useToast } from "../../contexts/ToastContext";

export interface BudgetKeyItem {
  id: string;
  name: string;
  masked_key: string;
  enabled: boolean;
  status: string;
  worker_selection_mode: string;
  routing_policy: string;
  rate_limit_rpm?: number;
  max_budget_usd?: number | null;
  spend_usd?: number;
  value_saved_usd?: number;
  budget_reset_period?: string | null;
  budget_exceeded_action?: string;
  spend_velocity_limit_usd?: number | null;
  spend_velocity_window_sec?: number;
  created_at?: string;
  last_used_at?: string;
}

interface BudgetGovernanceViewProps {
  apiKeys: BudgetKeyItem[];
  onRefresh: () => void;
  loading: boolean;
  gatewayTotalSaved?: number;
  gatewayTotalSpend?: number;
}

export function BudgetGovernanceView({
  apiKeys,
  onRefresh,
  loading,
  gatewayTotalSaved,
  gatewayTotalSpend,
}: BudgetGovernanceViewProps) {
  const { toast } = useToast();
  const [selectedKeyForBudget, setSelectedKeyForBudget] = useState<BudgetKeyItem | null>(null);
  const [resettingKeyId, setResettingKeyId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "CAPPED" | "WARNING" | "ACTIVE">("ALL");
  const [sortBy, setSortBy] = useState<"spend" | "saved" | "name">("spend");
  const [expandedKeyIds, setExpandedKeyIds] = useState<Record<string, boolean>>({});
  const [showTelemetryDrawer, setShowTelemetryDrawer] = useState(false);
  const [quickSavingKeyId, setQuickSavingKeyId] = useState<string | null>(null);

  // Aggregates & Analytics
  const totalBilledSpend = useMemo(() => {
    const fromKeys = apiKeys.reduce((acc, k) => acc + (k.spend_usd || 0), 0);
    if (gatewayTotalSpend != null && gatewayTotalSpend > 0) {
      return Math.max(fromKeys, gatewayTotalSpend);
    }
    return fromKeys;
  }, [apiKeys, gatewayTotalSpend]);

  const totalValueSaved = useMemo(() => {
    const fromKeys = apiKeys.reduce((acc, k) => acc + (k.value_saved_usd || 0), 0);
    if (gatewayTotalSaved != null && gatewayTotalSaved > 0) {
      return Math.max(fromKeys, gatewayTotalSaved);
    }
    return fromKeys;
  }, [apiKeys, gatewayTotalSaved]);

  const cappedKeysCount = useMemo(() => {
    return apiKeys.filter((k) => k.max_budget_usd != null && Number(k.max_budget_usd) > 0).length;
  }, [apiKeys]);

  const velocityActiveCount = useMemo(() => {
    return apiKeys.filter((k) => k.spend_velocity_limit_usd != null && Number(k.spend_velocity_limit_usd) > 0).length;
  }, [apiKeys]);

  const nearCapKeysCount = useMemo(() => {
    return apiKeys.filter((k) => {
      const cap = Number(k.max_budget_usd || 0);
      const spend = Number(k.spend_usd || 0);
      return cap > 0 && spend / cap >= 0.75;
    }).length;
  }, [apiKeys]);

  const activeKeysCount = useMemo(() => {
    return apiKeys.filter((k) => k.enabled && k.status === "active").length;
  }, [apiKeys]);

  // Filtered & Sorted keys
  const processedKeys = useMemo(() => {
    let result = apiKeys.filter((k) => {
      const matchesSearch =
        searchQuery.trim() === "" ||
        k.name.toLowerCase().includes(searchQuery.toLowerCase().trim()) ||
        k.masked_key.toLowerCase().includes(searchQuery.toLowerCase().trim());

      if (!matchesSearch) return false;

      if (statusFilter === "CAPPED") {
        return k.max_budget_usd != null && Number(k.max_budget_usd) > 0;
      }
      if (statusFilter === "WARNING") {
        const cap = Number(k.max_budget_usd || 0);
        const spend = Number(k.spend_usd || 0);
        return cap > 0 && spend / cap >= 0.75;
      }
      if (statusFilter === "ACTIVE") {
        return k.enabled && k.status === "active";
      }
      return true;
    });

    result.sort((a, b) => {
      if (sortBy === "spend") {
        return (b.spend_usd || 0) - (a.spend_usd || 0);
      }
      if (sortBy === "saved") {
        return (b.value_saved_usd || 0) - (a.value_saved_usd || 0);
      }
      return a.name.localeCompare(b.name);
    });

    return result;
  }, [apiKeys, searchQuery, statusFilter, sortBy]);

  const toggleExpand = (id: string) => {
    setExpandedKeyIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleResetSpend = async (key: BudgetKeyItem) => {
    setResettingKeyId(key.id);
    try {
      await apiClient.post(`/api/apikeys/${key.id}/reset-spend`);
      toast({
        title: "Spend Balance Reset",
        description: `Billed spend for ${key.name} has been reset to $0.00`,
        type: "success",
      });
      onRefresh();
    } catch (err: any) {
      toast({
        title: "Reset Failed",
        description: err.data?.detail || err.message || "Failed to reset spend balance",
        type: "error",
      });
    } finally {
      setResettingKeyId(null);
    }
  };

  const handleQuickBudgetPreset = async (key: BudgetKeyItem, presetVal: number | null) => {
    setQuickSavingKeyId(key.id);
    try {
      await apiClient.patch(`/api/apikeys/${key.id}`, { max_budget_usd: presetVal });
      toast({
        title: "Cap Updated",
        description: presetVal != null ? `Set ${key.name} hard cap to $${presetVal.toFixed(2)}` : `Set ${key.name} to Uncapped`,
        type: "success",
      });
      onRefresh();
    } catch (err: any) {
      toast({
        title: "Update Failed",
        description: err.data?.detail || err.message || "Could not update cap preset",
        type: "error",
      });
    } finally {
      setQuickSavingKeyId(null);
    }
  };

  return (
    <Tooltip.Provider delayDuration={150}>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {/* Top Controller Bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            backgroundColor: "var(--bg-surface)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            padding: "0.75rem 1.125rem",
            gap: "1rem",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  backgroundColor: "var(--success)",
                  boxShadow: "0 0 10px var(--success)",
                }}
              />
              <span className="font-mono" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                DUAL-ACCOUNTING PRICING ENGINE
              </span>
            </div>
            <span style={{ color: "var(--border-default)" }}>|</span>
            <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
              Real-time Upstream Metering · Sliding RPM & Velocity Breakers Active
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              type="button"
              className="btn btn-secondary btn-xs flex items-center gap-1"
              onClick={() => setShowTelemetryDrawer(true)}
              title="Inspect RFC HTTP Telemetry Response Headers"
              style={{ fontSize: "0.6875rem", padding: "0.25rem 0.55rem" }}
            >
              <Activity size={12} style={{ color: "var(--accent)" }} />
              <span>Telemetry Headers Spec</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-xs flex items-center gap-1"
              onClick={onRefresh}
              disabled={loading}
              title="Refresh budget accounting telemetry"
              style={{ fontSize: "0.6875rem", padding: "0.25rem 0.55rem" }}
            >
              <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
              <span>{loading ? "Syncing..." : "Sync"}</span>
            </button>
          </div>
        </div>

        {/* Executive Financial Metric Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "1rem" }}>
          {/* Card 1: Billed Spend (Paid Keys) */}
          <div className="operational-card fade-in">
            <div className="op-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                <div
                  style={{
                    width: "22px",
                    height: "22px",
                    borderRadius: "var(--radius-xs)",
                    backgroundColor: "var(--accent-muted)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <DollarSign size={13} style={{ color: "var(--accent)" }} />
                </div>
                <span>BILLED SPEND (PAID)</span>
              </div>
              <span className="font-mono" style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                USD ACCRUAL
              </span>
            </div>
            <div className="op-card-main" style={{ marginTop: "0.25rem" }}>
              <span className="op-card-val" style={{ color: "var(--text-primary)" }}>
                ${totalBilledSpend.toFixed(4)}
              </span>
              <span className="text-secondary font-mono text-xs">billed usage</span>
            </div>
            <div className="op-card-footer">
              <span>
                Uncapped Keys: <strong className="font-mono text-primary">{apiKeys.length - cappedKeysCount}</strong>
              </span>
              <span style={{ color: "var(--text-tertiary)" }}>
                Across {apiKeys.length} provisioned tokens
              </span>
            </div>
          </div>

          {/* Card 2: Commercial Value Saved */}
          <div className="operational-card fade-in">
            <div className="op-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                <div
                  style={{
                    width: "22px",
                    height: "22px",
                    borderRadius: "var(--radius-xs)",
                    backgroundColor: "var(--success-muted)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <PiggyBank size={13} style={{ color: "var(--success)" }} />
                </div>
                <span>COMMERCIAL VALUE SAVED</span>
              </div>
              <span className="op-card-trend up" style={{ color: "var(--success)" }}>
                <Sparkles size={11} /> 100% Free · All-Time
              </span>
            </div>
            <div className="op-card-main" style={{ marginTop: "0.25rem", display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
              <span className="op-card-val font-mono" style={{ color: "var(--success)" }}>
                +${totalValueSaved.toFixed(4)}
              </span>
              <span className="text-secondary font-mono text-xs">retail avoided</span>
            </div>
            <div className="op-card-footer" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
              <span>
                Free Tiers & Semantic Cache
              </span>
              <span style={{ color: "var(--success)" }}>Active Savings</span>
            </div>
          </div>

          {/* Card 3: Hard Budget Caps */}
          <div className="operational-card fade-in">
            <div className="op-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                <div
                  style={{
                    width: "22px",
                    height: "22px",
                    borderRadius: "var(--radius-xs)",
                    backgroundColor: "var(--bg-elevated)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Sliders size={13} style={{ color: "var(--text-primary)" }} />
                </div>
                <span>HARD SPEND CAPS</span>
              </div>
              <span
                className="font-mono"
                style={{
                  fontSize: "0.625rem",
                  color: nearCapKeysCount > 0 ? "var(--warning)" : "var(--text-tertiary)",
                }}
              >
                {nearCapKeysCount > 0 ? `⚠ ${nearCapKeysCount} NEAR CAP` : "HEALTHY"}
              </span>
            </div>
            <div className="op-card-main" style={{ marginTop: "0.25rem" }}>
              <span className="op-card-val">
                {cappedKeysCount} <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-tertiary)" }}>/ {apiKeys.length}</span>
              </span>
              <span className="text-secondary font-mono text-xs">keys governed</span>
            </div>
            <div className="op-card-footer">
              <span>
                Pre-flight 429: <strong className="font-mono text-primary">Enforced</strong>
              </span>
              <span style={{ color: "var(--text-tertiary)" }}>Fallback to Free</span>
            </div>
          </div>

          {/* Card 4: Loop Velocity Circuit Breakers */}
          <div className="operational-card fade-in">
            <div className="op-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                <div
                  style={{
                    width: "22px",
                    height: "22px",
                    borderRadius: "var(--radius-xs)",
                    backgroundColor: "var(--warning-muted)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <ShieldAlert size={13} style={{ color: "var(--warning)" }} />
                </div>
                <span>VELOCITY CIRCUIT BREAKERS</span>
              </div>
              <span className="font-mono" style={{ fontSize: "0.625rem", color: "var(--warning)" }}>
                ANTI-RUNAWAY
              </span>
            </div>
            <div className="op-card-main" style={{ marginTop: "0.25rem" }}>
              <span className="op-card-val">
                {velocityActiveCount} <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-tertiary)" }}>active</span>
              </span>
              <span className="text-secondary font-mono text-xs">monitoring $/min</span>
            </div>
            <div className="op-card-footer">
              <span>
                Sliding Window: <strong className="font-mono text-primary">60 sec</strong>
              </span>
              <span style={{ color: "var(--text-tertiary)" }}>Halt Infinite Loops</span>
            </div>
          </div>
        </div>

        {/* Dynamic Key Budget Matrix Section */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {/* Section Toolbar */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
            }}
          >
            {/* Search Box */}
            <div className="search-input-wrap" style={{ maxWidth: "340px", flex: 1 }}>
              <Search size={13} />
              <input
                type="text"
                className="search-input"
                placeholder="Search key by name or prefix..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* Filter Pills & Sort Selector */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
              <div className="filter-btn-group">
                <button
                  type="button"
                  className={`filter-btn ${statusFilter === "ALL" ? "active" : ""}`}
                  onClick={() => setStatusFilter("ALL")}
                >
                  All ({apiKeys.length})
                </button>
                <button
                  type="button"
                  className={`filter-btn ${statusFilter === "ACTIVE" ? "active" : ""}`}
                  onClick={() => setStatusFilter("ACTIVE")}
                >
                  Active ({activeKeysCount})
                </button>
                <button
                  type="button"
                  className={`filter-btn ${statusFilter === "CAPPED" ? "active" : ""}`}
                  onClick={() => setStatusFilter("CAPPED")}
                >
                  Hard Capped ({cappedKeysCount})
                </button>
                <button
                  type="button"
                  className={`filter-btn ${statusFilter === "WARNING" ? "active" : ""}`}
                  onClick={() => setStatusFilter("WARNING")}
                >
                  Near Limit ({nearCapKeysCount})
                </button>
              </div>

              {/* Sort By Dropdown */}
              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>
                  <ArrowUpDown size={11} />
                </span>
                <select
                  className="form-select font-mono"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  style={{
                    fontSize: "0.6875rem",
                    padding: "0.2rem 0.5rem",
                    height: "28px",
                    backgroundColor: "var(--bg-surface)",
                    borderColor: "var(--border-subtle)",
                  }}
                >
                  <option value="spend">Sort: Highest Spend</option>
                  <option value="saved">Sort: Highest Value Saved</option>
                  <option value="name">Sort: Key Name</option>
                </select>
              </div>
            </div>
          </div>

          {/* Dynamic Cards Matrix List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <AnimatePresence mode="popLayout">
              {processedKeys.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="card"
                  style={{
                    padding: "3rem 1.5rem",
                    textAlign: "center",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "0.5rem",
                    backgroundColor: "var(--bg-surface)",
                  }}
                >
                  <DollarSign size={28} style={{ color: "var(--text-tertiary)", opacity: 0.4 }} />
                  <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    No Gateway API Keys Match Your Filter
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", maxWidth: "360px" }}>
                    Try clearing your search query or switching the status filter above.
                  </span>
                  {(searchQuery || statusFilter !== "ALL") && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => {
                        setSearchQuery("");
                        setStatusFilter("ALL");
                      }}
                      style={{ marginTop: "0.5rem" }}
                    >
                      Reset Filter Options
                    </button>
                  )}
                </motion.div>
              ) : (
                processedKeys.map((key) => {
                  const spend = key.spend_usd || 0;
                  const cap = key.max_budget_usd;
                  const isCapped = cap != null && Number(cap) > 0;
                  const percentUsed = isCapped ? Math.min(100, (spend / Number(cap)) * 100) : 0;
                  const isOverCap = isCapped && spend >= Number(cap);
                  const isWarning = isCapped && spend / Number(cap) >= 0.75;
                  const isResetting = resettingKeyId === key.id;
                  const isQuickSaving = quickSavingKeyId === key.id;
                  const isExpanded = Boolean(expandedKeyIds[key.id]);

                  const statusClass = key.status === "active" ? "active" : key.status === "revoked" ? "danger" : "warning";

                  return (
                    <motion.div
                      key={key.id}
                      layout
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.98 }}
                      transition={{ duration: 0.15 }}
                      whileHover={{
                        borderColor: isOverCap ? "var(--error)" : isWarning ? "var(--warning)" : "var(--border-default)",
                        boxShadow: "0 6px 24px rgba(0, 0, 0, 0.35)",
                      }}
                      style={{
                        backgroundColor: "var(--bg-surface)",
                        border: isOverCap
                          ? "1px solid var(--error-border)"
                          : isWarning
                          ? "1px solid var(--warning-border)"
                          : "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-md)",
                        padding: "1rem 1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.875rem",
                        boxShadow: isOverCap
                          ? "0 4px 16px rgba(239, 68, 68, 0.08)"
                          : "0 2px 8px rgba(0, 0, 0, 0.2)",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {/* Top Header Row of the Card */}
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "1rem",
                          flexWrap: "wrap",
                        }}
                      >
                        {/* Left Identity Group (NO COPY BUTTON as requested) */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
                          {/* Status Pill */}
                          <span className={`status-pill ${statusClass}`}>
                            <span className="status-pulse" />
                            {key.status?.toUpperCase() || "ACTIVE"}
                          </span>

                          {/* Key Name */}
                          <span style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                            {key.name}
                          </span>

                          {/* Token Identifier Chip (Clean Display Only - strictly no copy button) */}
                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.15rem 0.5rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-tertiary)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.35rem",
                            }}
                          >
                            <KeyRound size={11} style={{ opacity: 0.65 }} />
                            <span>{key.masked_key}</span>
                          </span>

                          {/* Scope / Policy Badges */}
                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.625rem",
                              padding: "0.15rem 0.45rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--bg-elevated)",
                              color: "var(--text-secondary)",
                              border: "1px solid var(--border-subtle)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                            }}
                          >
                            <Cpu size={10} style={{ color: "var(--text-tertiary)" }} />
                            <span>
                              {key.worker_selection_mode === "MODEL_GROUPS"
                                ? "Virtual Tiers"
                                : key.worker_selection_mode === "WORKER_POOL"
                                ? "Worker Pool"
                                : key.worker_selection_mode === "SPECIFIC_WORKER"
                                ? "Pinned Worker"
                                : "All Models (AUTO)"}
                            </span>
                          </span>

                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.625rem",
                              padding: "0.15rem 0.45rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--accent-muted)",
                              color: "var(--accent)",
                              border: "1px solid var(--accent-border)",
                              textTransform: "capitalize",
                            }}
                          >
                            {key.routing_policy || "balanced"}
                          </span>
                        </div>

                        {/* Right Governance Tags & Actions */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          {/* Action Pill on Cap */}
                          <Tooltip.Root>
                            <Tooltip.Trigger asChild>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                  padding: "0.2rem 0.5rem",
                                  borderRadius: "var(--radius-xs)",
                                  backgroundColor:
                                    key.budget_exceeded_action === "fallback_to_free"
                                      ? "var(--accent-muted)"
                                      : "var(--bg-canvas)",
                                  color:
                                    key.budget_exceeded_action === "fallback_to_free"
                                      ? "var(--accent)"
                                      : "var(--text-secondary)",
                                  border: `1px solid ${
                                    key.budget_exceeded_action === "fallback_to_free"
                                      ? "var(--accent-border)"
                                      : "var(--border-subtle)"
                                  }`,
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.35rem",
                                  cursor: "help",
                                }}
                              >
                                <span
                                  style={{
                                    width: "5px",
                                    height: "5px",
                                    borderRadius: "50%",
                                    backgroundColor:
                                      key.budget_exceeded_action === "fallback_to_free"
                                        ? "var(--accent)"
                                        : "var(--text-tertiary)",
                                  }}
                                />
                                <span>
                                  {key.budget_exceeded_action === "fallback_to_free"
                                    ? "Fallback to Free"
                                    : "Hard Cap (429)"}
                                </span>
                              </span>
                            </Tooltip.Trigger>
                            <Tooltip.Portal>
                              <Tooltip.Content
                                style={{
                                  backgroundColor: "var(--bg-elevated)",
                                  color: "var(--text-primary)",
                                  padding: "0.4rem 0.65rem",
                                  borderRadius: "var(--radius-sm)",
                                  fontSize: "0.6875rem",
                                  boxShadow: "var(--shadow-popover)",
                                  border: "1px solid var(--border-default)",
                                  zIndex: 10000,
                                }}
                              >
                                {key.budget_exceeded_action === "fallback_to_free"
                                  ? "When cap is reached, requests automatically route to free-tier instances"
                                  : "When cap is reached, requests are immediately rejected with HTTP 429 budget error"}
                                <Tooltip.Arrow style={{ fill: "var(--bg-elevated)" }} />
                              </Tooltip.Content>
                            </Tooltip.Portal>
                          </Tooltip.Root>

                          {/* Reset Cycle Pill */}
                          <span
                            className="font-mono"
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-secondary)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              textTransform: "capitalize",
                            }}
                          >
                            <Clock size={11} style={{ color: "var(--text-tertiary)" }} />
                            <span>{key.budget_reset_period || "Monthly"}</span>
                          </span>

                          {/* Configure Budget Button */}
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs flex items-center gap-1"
                            onClick={() => setSelectedKeyForBudget(key)}
                            title="Configure spending cap, reset period, and circuit breakers"
                            style={{ padding: "0.3rem 0.6rem" }}
                          >
                            <Sliders size={12} style={{ color: "var(--accent)" }} />
                            <span>Edit Budget</span>
                          </button>

                          {/* Reset Spend Button */}
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs flex items-center gap-1"
                            onClick={() => handleResetSpend(key)}
                            disabled={isResetting || spend === 0}
                            title="Reset accumulated billed spend back to $0.00"
                            style={{ padding: "0.3rem 0.55rem" }}
                          >
                            <RotateCcw size={11} className={isResetting ? "animate-spin" : ""} />
                            <span>{isResetting ? "Resetting..." : "Reset"}</span>
                          </button>

                          {/* Quick Presets & Insights Toggle Button */}
                          <button
                            type="button"
                            className={`btn btn-xs flex items-center gap-1.5 ${isExpanded ? "btn-primary" : "btn-secondary"}`}
                            onClick={() => toggleExpand(key.id)}
                            title={isExpanded ? "Collapse inline quick adjustments" : "Expand inline quick presets & diagnostics"}
                            style={{ fontSize: "0.6875rem", padding: "0.3rem 0.65rem" }}
                          >
                            <span>Quick Presets</span>
                            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                          </button>
                        </div>
                      </div>

                      {/* Telemetry Gauge Panels (3 Distinct High-Fidelity Instruments) */}
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
                          gap: "0.75rem",
                        }}
                      >
                        {/* Column 1: Live Spend vs Hard Cap Gauge */}
                        <div
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            border: isOverCap
                              ? "1px solid var(--error-border)"
                              : isWarning
                              ? "1px solid var(--warning-border)"
                              : "1px solid var(--border-subtle)",
                            borderRadius: "var(--radius-sm)",
                            padding: "0.85rem 1rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.45rem",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                              <div
                                style={{
                                  width: "20px",
                                  height: "20px",
                                  borderRadius: "var(--radius-xs)",
                                  backgroundColor: isOverCap
                                    ? "var(--error-muted)"
                                    : isWarning
                                    ? "var(--warning-muted)"
                                    : "var(--accent-muted)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                }}
                              >
                                <DollarSign
                                  size={12}
                                  style={{
                                    color: isOverCap
                                      ? "var(--error)"
                                      : isWarning
                                      ? "var(--warning)"
                                      : "var(--accent)",
                                  }}
                                />
                              </div>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                  color: "var(--text-tertiary)",
                                  textTransform: "uppercase",
                                  letterSpacing: "0.04em",
                                }}
                              >
                                Billed Spend Meter
                              </span>
                            </div>

                            <span
                              className="font-mono"
                              style={{
                                fontSize: "0.625rem",
                                fontWeight: 700,
                                padding: "0.1rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                                backgroundColor: isOverCap
                                  ? "var(--error-muted)"
                                  : isWarning
                                  ? "var(--warning-muted)"
                                  : isCapped
                                  ? "var(--accent-muted)"
                                  : "var(--bg-elevated)",
                                color: isOverCap
                                  ? "var(--error)"
                                  : isWarning
                                  ? "var(--warning)"
                                  : isCapped
                                  ? "var(--accent)"
                                  : "var(--text-secondary)",
                                border: `1px solid ${
                                  isOverCap
                                    ? "var(--error-border)"
                                    : isWarning
                                    ? "var(--warning-border)"
                                    : isCapped
                                    ? "var(--accent-border)"
                                    : "var(--border-subtle)"
                                }`,
                              }}
                            >
                              {isCapped ? `${percentUsed.toFixed(0)}% USED` : "UNCAPPED ∞"}
                            </span>
                          </div>

                          <div style={{ display: "flex", alignItems: "baseline", gap: "0.35rem", marginTop: "0.1rem" }}>
                            <span
                              className="font-mono"
                              style={{
                                fontSize: "1.25rem",
                                fontWeight: 700,
                                color: isOverCap ? "var(--error)" : isWarning ? "var(--warning)" : "var(--text-primary)",
                              }}
                            >
                              ${spend.toFixed(4)}
                            </span>
                            <span className="font-mono text-tertiary" style={{ fontSize: "0.75rem" }}>
                              {isCapped ? `/ $${Number(cap).toFixed(2)} cap` : "(Unlimited Ceiling)"}
                            </span>
                          </div>

                          {/* Dynamic Visual Progress Bar */}
                          <div
                            style={{
                              width: "100%",
                              height: "6px",
                              backgroundColor: "var(--bg-elevated)",
                              borderRadius: "3px",
                              overflow: "hidden",
                              marginTop: "0.1rem",
                            }}
                          >
                            {isCapped ? (
                              <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${percentUsed}%` }}
                                transition={{ duration: 0.4, ease: "easeOut" }}
                                style={{
                                  height: "100%",
                                  backgroundColor: isOverCap
                                    ? "var(--error)"
                                    : isWarning
                                    ? "var(--warning)"
                                    : "var(--success)",
                                }}
                              />
                            ) : (
                              <div
                                style={{
                                  width: "100%",
                                  height: "100%",
                                  background:
                                    "repeating-linear-gradient(45deg, rgba(59, 130, 246, 0.22), rgba(59, 130, 246, 0.22) 6px, rgba(59, 130, 246, 0.06) 6px, rgba(59, 130, 246, 0.06) 12px)",
                                }}
                              />
                            )}
                          </div>

                          <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                            {isCapped
                              ? isOverCap
                                ? "Cap reached · pre-flight 429 enforced"
                                : `$${(Number(cap) - spend).toFixed(4)} remaining headroom`
                              : "No hard ceiling enforced · live metering"}
                          </span>
                        </div>

                        {/* Column 2: Commercial Value Saved */}
                        <div
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "var(--radius-sm)",
                            padding: "0.85rem 1rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.45rem",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                              <div
                                style={{
                                  width: "20px",
                                  height: "20px",
                                  borderRadius: "var(--radius-xs)",
                                  backgroundColor: "var(--success-muted)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                }}
                              >
                                <PiggyBank size={12} style={{ color: "var(--success)" }} />
                              </div>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                  color: "var(--text-tertiary)",
                                  textTransform: "uppercase",
                                  letterSpacing: "0.04em",
                                }}
                              >
                                Commercial Savings
                              </span>
                            </div>

                            <span
                              className="font-mono"
                              style={{
                                fontSize: "0.625rem",
                                fontWeight: 700,
                                padding: "0.1rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                                backgroundColor: (key.value_saved_usd || 0) > 0 ? "var(--success-muted)" : "var(--bg-elevated)",
                                color: (key.value_saved_usd || 0) > 0 ? "var(--success)" : "var(--text-secondary)",
                                border: `1px solid ${
                                  (key.value_saved_usd || 0) > 0 ? "var(--success-border)" : "var(--border-subtle)"
                                }`,
                              }}
                            >
                              {(key.value_saved_usd || 0) > 0 ? "RETAIL AVOIDED" : "ZERO-COST POOL"}
                            </span>
                          </div>

                          <div style={{ display: "flex", alignItems: "baseline", gap: "0.35rem", marginTop: "0.1rem" }}>
                            <span
                              className="font-mono"
                              style={{
                                fontSize: "1.25rem",
                                fontWeight: 700,
                                color: "var(--success)",
                              }}
                            >
                              +${(key.value_saved_usd || 0).toFixed(4)}
                            </span>
                            <span className="font-mono text-tertiary" style={{ fontSize: "0.75rem" }}>
                              commercial value
                            </span>
                          </div>

                          <div
                            style={{
                              width: "100%",
                              height: "6px",
                              backgroundColor: "var(--bg-elevated)",
                              borderRadius: "3px",
                              overflow: "hidden",
                              marginTop: "0.1rem",
                            }}
                          >
                            <div
                              style={{
                                width: (key.value_saved_usd || 0) > 0 ? "100%" : "0%",
                                height: "100%",
                                backgroundColor: "var(--success)",
                                transition: "width 0.4s ease-out",
                              }}
                            />
                          </div>

                          <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                            Accrued via free provider tiers & cache
                          </span>
                        </div>

                        {/* Column 3: Runaway Loop Protection */}
                        <div
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            border:
                              key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                ? "1px solid var(--warning-border)"
                                : "1px solid var(--border-subtle)",
                            borderRadius: "var(--radius-sm)",
                            padding: "0.85rem 1rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.45rem",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                              <div
                                style={{
                                  width: "20px",
                                  height: "20px",
                                  borderRadius: "var(--radius-xs)",
                                  backgroundColor:
                                    key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                      ? "var(--warning-muted)"
                                      : "var(--bg-elevated)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                }}
                              >
                                <ShieldAlert
                                  size={12}
                                  style={{
                                    color:
                                      key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                        ? "var(--warning)"
                                        : "var(--text-tertiary)",
                                  }}
                                />
                              </div>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                  color: "var(--text-tertiary)",
                                  textTransform: "uppercase",
                                  letterSpacing: "0.04em",
                                }}
                              >
                                Velocity Circuit Breaker
                              </span>
                            </div>

                            <span
                              className="font-mono"
                              style={{
                                fontSize: "0.625rem",
                                fontWeight: 700,
                                padding: "0.1rem 0.45rem",
                                borderRadius: "var(--radius-xs)",
                                backgroundColor:
                                  key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                    ? "var(--warning-muted)"
                                    : "var(--bg-elevated)",
                                color:
                                  key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                    ? "var(--warning)"
                                    : "var(--text-secondary)",
                                border: `1px solid ${
                                  key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                    ? "var(--warning-border)"
                                    : "var(--border-subtle)"
                                }`,
                              }}
                            >
                              {key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                ? "CIRCUIT ACTIVE"
                                : "UNRESTRICTED"}
                            </span>
                          </div>

                          <div style={{ display: "flex", alignItems: "baseline", gap: "0.35rem", marginTop: "0.1rem" }}>
                            <span
                              className="font-mono"
                              style={{
                                fontSize: "1.25rem",
                                fontWeight: 700,
                                color:
                                  key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                    ? "var(--warning)"
                                    : "var(--text-secondary)",
                              }}
                            >
                              {key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                ? `$${Number(key.spend_velocity_limit_usd).toFixed(2)}/min`
                                : "Unmetered"}
                            </span>
                            <span className="font-mono text-tertiary" style={{ fontSize: "0.75rem" }}>
                              {key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                ? "(60s sliding window)"
                                : "(No burst ceiling)"}
                            </span>
                          </div>

                          <div
                            style={{
                              width: "100%",
                              height: "6px",
                              backgroundColor: "var(--bg-elevated)",
                              borderRadius: "3px",
                              overflow: "hidden",
                              marginTop: "0.1rem",
                            }}
                          >
                            <div
                              style={{
                                width:
                                  key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                                    ? "100%"
                                    : "0%",
                                height: "100%",
                                backgroundColor: "var(--warning)",
                                transition: "width 0.4s ease-out",
                              }}
                            />
                          </div>

                          <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                            {key.spend_velocity_limit_usd != null && Number(key.spend_velocity_limit_usd) > 0
                              ? "Halts rapid loops exceeding threshold in rolling 60s"
                              : "No runaway loop governor configured"}
                          </span>
                        </div>
                      </div>

                      {/* Expandable Deep Telemetry & Quick Adjust Tray */}
                      <AnimatePresence>
                        {isExpanded && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.2, ease: "easeOut" }}
                            style={{
                              overflow: "hidden",
                              borderTop: "1px dashed var(--border-subtle)",
                              paddingTop: "0.75rem",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.75rem",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                gap: "1rem",
                                flexWrap: "wrap",
                              }}
                            >
                              {/* 1-Click Quick Budget Presets */}
                              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", flexWrap: "wrap" }}>
                                <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                                  Quick Adjust Cap:
                                </span>
                                {[
                                  { label: "Uncapped", val: null },
                                  { label: "$5", val: 5 },
                                  { label: "$25", val: 25 },
                                  { label: "$100", val: 100 },
                                  { label: "$500", val: 500 },
                                ].map((p) => {
                                  const isSelected =
                                    (p.val === null && (key.max_budget_usd == null || key.max_budget_usd === 0)) ||
                                    (p.val !== null && Number(key.max_budget_usd) === p.val);
                                  return (
                                    <button
                                      key={p.label}
                                      type="button"
                                      className={`btn btn-xs ${isSelected ? "btn-primary" : "btn-secondary"}`}
                                      disabled={isQuickSaving}
                                      onClick={() => handleQuickBudgetPreset(key, p.val)}
                                      style={{ fontSize: "0.65625rem", padding: "0.2rem 0.5rem" }}
                                    >
                                      {p.label}
                                    </button>
                                  );
                                })}
                              </div>

                              {/* Key Rate Limit & Timestamp Diagnostics */}
                              <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                                <span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>
                                  Sliding Limit: <strong className="text-secondary">{key.rate_limit_rpm || 120} RPM</strong>
                                </span>
                                <span className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>
                                  Created: {key.created_at ? new Date(key.created_at).toLocaleDateString() : "Active"}
                                </span>
                              </div>
                            </div>

                            {/* Architectural Enforcement Impact Note */}
                            <div
                              style={{
                                backgroundColor: "var(--bg-canvas)",
                                border: "1px solid var(--border-subtle)",
                                borderRadius: "var(--radius-xs)",
                                padding: "0.55rem 0.75rem",
                                fontSize: "0.6875rem",
                                color: "var(--text-secondary)",
                                display: "flex",
                                alignItems: "center",
                                gap: "0.5rem",
                              }}
                            >
                              <Info size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                              <span>
                                {isCapped
                                  ? key.budget_exceeded_action === "fallback_to_free"
                                    ? `When spending exceeds $${Number(cap).toFixed(2)}, requests bearing this key will automatically route to zero-cost models without rejecting clients.`
                                    : `When spending exceeds $${Number(cap).toFixed(2)}, WRAP will reject client requests pre-flight with HTTP 429 and error code 'budget_cap_exceeded'.`
                                  : "This key has no hard spending cap. It can consume paid frontier models continuously up to upstream provider limits."}
                              </span>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  );
                })
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Telemetry Protocol Modal */}
        <Dialog.Root open={showTelemetryDrawer} onOpenChange={setShowTelemetryDrawer}>
          <AnimatePresence>
            {showTelemetryDrawer && (
              <Dialog.Portal forceMount>
                <Dialog.Overlay asChild>
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: "fixed",
                      inset: 0,
                      backgroundColor: "rgba(0, 0, 0, 0.75)",
                      backdropFilter: "blur(4px)",
                      zIndex: 1000,
                    }}
                  />
                </Dialog.Overlay>

                <div
                  style={{
                    position: "fixed",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    zIndex: 1001,
                    padding: "1rem",
                    pointerEvents: "none",
                  }}
                >
                  <Dialog.Content asChild>
                    <motion.div
                      initial={{ opacity: 0, scale: 0.96, y: 12 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.96, y: 12 }}
                      transition={{ duration: 0.18, ease: "easeOut" }}
                      style={{
                        width: "100%",
                        maxWidth: "640px",
                        backgroundColor: "var(--bg-surface)",
                        border: "1px solid var(--border-default)",
                        borderRadius: "var(--radius-lg)",
                        boxShadow: "0 24px 64px rgba(0, 0, 0, 0.65)",
                        display: "flex",
                        flexDirection: "column",
                        pointerEvents: "auto",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          padding: "1rem 1.25rem",
                          borderBottom: "1px solid var(--border-subtle)",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <Activity size={17} style={{ color: "var(--accent)" }} />
                          <Dialog.Title style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            Dual-Accounting Protocol & Telemetry Headers Spec
                          </Dialog.Title>
                        </div>
                        <Dialog.Close asChild>
                          <button className="btn btn-ghost btn-sm" aria-label="Close" style={{ padding: "0.25rem" }}>
                            <X size={15} />
                          </button>
                        </Dialog.Close>
                      </div>

                      <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
                        <p style={{ margin: 0, fontSize: "0.78125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                          WRAP automatically calculates upstream provider billing and injects granular economic accounting telemetry headers into every client completion response:
                        </p>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-subtle)",
                              borderRadius: "var(--radius-sm)",
                              padding: "0.75rem 1rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span className="font-mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                X-Cost-USD: 0.0042
                              </span>
                              <span className="font-mono text-tertiary" style={{ fontSize: "0.625rem" }}>
                                FLOAT ($ USD)
                              </span>
                            </div>
                            <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginTop: "0.25rem", display: "block" }}>
                              Real billable cost charged by the upstream provider for this specific completion. $0.0000 on free-tier workers or cache hits.
                            </span>
                          </div>

                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-subtle)",
                              borderRadius: "var(--radius-sm)",
                              padding: "0.75rem 1rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span className="font-mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--success)" }}>
                                X-Value-Saved-USD: 0.0150
                              </span>
                              <span className="font-mono text-tertiary" style={{ fontSize: "0.625rem" }}>
                                FLOAT ($ USD)
                              </span>
                            </div>
                            <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginTop: "0.25rem", display: "block" }}>
                              Equivalent commercial market retail cost avoided by routing through free-tier quotas or retrieving from prompt cache.
                            </span>
                          </div>

                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-subtle)",
                              borderRadius: "var(--radius-sm)",
                              padding: "0.75rem 1rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span className="font-mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--accent)" }}>
                                X-Cache: HIT | MISS
                              </span>
                              <span className="font-mono text-tertiary" style={{ fontSize: "0.625rem" }}>
                                STRING
                              </span>
                            </div>
                            <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginTop: "0.25rem", display: "block" }}>
                              Denotes whether the request was served instantly via WRAP semantic memory cache (zero cost, sub-10ms response).
                            </span>
                          </div>
                        </div>

                        <div
                          style={{
                            backgroundColor: "var(--bg-elevated)",
                            borderRadius: "var(--radius-sm)",
                            padding: "0.75rem",
                            fontSize: "0.71875rem",
                            color: "var(--text-secondary)",
                            display: "flex",
                            alignItems: "flex-start",
                            gap: "0.5rem",
                          }}
                        >
                          <Info size={14} style={{ color: "var(--accent)", flexShrink: 0, marginTop: "0.1rem" }} />
                          <span>
                            Clients can read these headers in real-time to compute token billing, pass cost telemetry to end customers, or monitor automated cost savings.
                          </span>
                        </div>
                      </div>

                      <div
                        style={{
                          borderTop: "1px solid var(--border-subtle)",
                          padding: "0.75rem 1.25rem",
                          display: "flex",
                          justifyContent: "flex-end",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowTelemetryDrawer(false)}>
                          Close Spec
                        </button>
                      </div>
                    </motion.div>
                  </Dialog.Content>
                </div>
              </Dialog.Portal>
            )}
          </AnimatePresence>
        </Dialog.Root>

        {/* Edit Budget Modal */}
        {selectedKeyForBudget && (
          <EditKeyBudgetModal
            apiKey={selectedKeyForBudget}
            isOpen={Boolean(selectedKeyForBudget)}
            onClose={() => setSelectedKeyForBudget(null)}
            onUpdated={() => {
              setSelectedKeyForBudget(null);
              onRefresh();
            }}
          />
        )}
      </div>
    </Tooltip.Provider>
  );
}

interface EditKeyBudgetModalProps {
  apiKey: BudgetKeyItem;
  isOpen: boolean;
  onClose: () => void;
  onUpdated: () => void;
}

function EditKeyBudgetModal({ apiKey, isOpen, onClose, onUpdated }: EditKeyBudgetModalProps) {
  const { toast } = useToast();
  const [maxBudgetUsd, setMaxBudgetUsd] = useState(
    apiKey.max_budget_usd != null ? String(apiKey.max_budget_usd) : ""
  );
  const [budgetResetPeriod, setBudgetResetPeriod] = useState(apiKey.budget_reset_period || "monthly");
  const [budgetExceededAction, setBudgetExceededAction] = useState(apiKey.budget_exceeded_action || "hard_cap");
  const [spendVelocityLimitUsd, setSpendVelocityLimitUsd] = useState(
    apiKey.spend_velocity_limit_usd != null ? String(apiKey.spend_velocity_limit_usd) : ""
  );
  const [currentSpendUsd, setCurrentSpendUsd] = useState(apiKey.spend_usd || 0.0);
  const [isResettingSpend, setIsResettingSpend] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleResetSpend = async () => {
    setIsResettingSpend(true);
    try {
      await apiClient.post(`/api/apikeys/${apiKey.id}/reset-spend`);
      setCurrentSpendUsd(0.0);
      toast({
        title: "Spend Balance Reset",
        description: `Current billed spend for ${apiKey.name} has been reset to $0.00`,
        type: "success",
      });
    } catch (err: any) {
      toast({
        title: "Reset Failed",
        description: err.data?.detail || err.message || "Failed to reset spend balance",
        type: "error",
      });
    } finally {
      setIsResettingSpend(false);
    }
  };

  const handleSaveBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const parsedBudget = maxBudgetUsd.trim() === "" ? null : Number(maxBudgetUsd);
      const parsedVelocity = spendVelocityLimitUsd.trim() === "" ? null : Number(spendVelocityLimitUsd);

      const payload = {
        max_budget_usd: isNaN(parsedBudget as any) ? null : parsedBudget,
        budget_reset_period: budgetResetPeriod,
        budget_exceeded_action: budgetExceededAction,
        spend_velocity_limit_usd: isNaN(parsedVelocity as any) ? null : parsedVelocity,
      };

      await apiClient.patch(`/api/apikeys/${apiKey.id}`, payload);
      toast({
        title: "Budget Settings Updated",
        description: `Successfully configured financial governance for ${apiKey.name}`,
        type: "success",
      });
      onUpdated();
    } catch (err: any) {
      toast({
        title: "Update Failed",
        description: err.data?.detail || err.message || "Failed to update budget settings",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <AnimatePresence>
        {isOpen && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{
                  position: "fixed",
                  inset: 0,
                  backgroundColor: "rgba(0, 0, 0, 0.75)",
                  backdropFilter: "blur(4px)",
                  zIndex: 1000,
                }}
              />
            </Dialog.Overlay>

            <div
              style={{
                position: "fixed",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1001,
                padding: "1rem",
                pointerEvents: "none",
              }}
            >
              <Dialog.Content asChild>
                <motion.div
                  initial={{ opacity: 0, scale: 0.96, y: 12 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.96, y: 12 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  style={{
                    width: "100%",
                    maxWidth: "600px",
                    maxHeight: "90vh",
                    backgroundColor: "var(--bg-surface)",
                    border: "1px solid var(--border-default)",
                    borderRadius: "var(--radius-lg)",
                    boxShadow: "0 24px 64px rgba(0, 0, 0, 0.65)",
                    display: "flex",
                    flexDirection: "column",
                    pointerEvents: "auto",
                    overflow: "hidden",
                  }}
                >
                  {/* Header */}
                  <div
                    style={{
                      padding: "1rem 1.25rem",
                      borderBottom: "1px solid var(--border-subtle)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <DollarSign size={17} style={{ color: "var(--accent)" }} />
                      <Dialog.Title
                        style={{
                          margin: 0,
                          fontSize: "0.9375rem",
                          fontWeight: 600,
                          color: "var(--text-primary)",
                        }}
                      >
                        Configure Key Budget & Spend Limits
                      </Dialog.Title>
                      <span
                        className="font-mono text-tertiary"
                        style={{
                          fontSize: "0.6875rem",
                          padding: "0.1rem 0.35rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor: "var(--bg-subtle)",
                        }}
                      >
                        {apiKey.name}
                      </span>
                    </div>

                    <Dialog.Close asChild>
                      <button
                        className="btn btn-ghost btn-sm"
                        aria-label="Close"
                        style={{ padding: "0.25rem", color: "var(--text-secondary)" }}
                      >
                        <X size={15} />
                      </button>
                    </Dialog.Close>
                  </div>

                  {/* Form */}
                  <form onSubmit={handleSaveBudget} style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
                    <div style={{ padding: "1.25rem", overflowY: "auto", display: "flex", flexDirection: "column", gap: "1.125rem" }}>
                      {/* Live Accounting Summary Box */}
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1.4fr 1.2fr auto",
                          gap: "0.75rem",
                          backgroundColor: "var(--bg-canvas)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-sm)",
                          padding: "0.75rem 1rem",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <div style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.2rem" }}>
                            Current Billed Spend
                          </div>
                          <div className="font-mono" style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                            ${currentSpendUsd.toFixed(4)}
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.2rem" }}>
                            Commercial Value Saved
                          </div>
                          <div className="font-mono" style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--success)" }}>
                            +${(apiKey.value_saved_usd || 0).toFixed(4)}
                          </div>
                        </div>

                        <div>
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs flex items-center gap-1"
                            onClick={handleResetSpend}
                            disabled={isResettingSpend || currentSpendUsd === 0}
                            title="Reset accumulated spend balance for this key back to $0.00"
                          >
                            <RotateCcw size={11} className={isResettingSpend ? "animate-spin" : ""} />
                            <span>{isResettingSpend ? "Resetting..." : "Reset Spend"}</span>
                          </button>
                        </div>
                      </div>

                      {/* Hard Spend Cap & Presets */}
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                            Hard Spend Cap ($ USD)
                          </label>
                          <span className="font-mono text-tertiary" style={{ fontSize: "0.625rem" }}>
                            Leave blank for uncapped usage
                          </span>
                        </div>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          className="form-input font-mono"
                          placeholder="e.g. 50.00 (or leave empty for uncapped)"
                          value={maxBudgetUsd}
                          onChange={(e) => setMaxBudgetUsd(e.target.value)}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.6rem", marginTop: "0.3rem" }}
                        />
                        <div className="filter-btn-group" style={{ marginTop: "0.4rem" }}>
                          {[
                            { label: "Uncapped", val: "" },
                            { label: "$5", val: "5.00" },
                            { label: "$25", val: "25.00" },
                            { label: "$100", val: "100.00" },
                            { label: "$500", val: "500.00" },
                          ].map((b) => (
                            <button
                              key={b.label}
                              type="button"
                              className={`filter-btn ${maxBudgetUsd === b.val ? "active" : ""}`}
                              onClick={() => setMaxBudgetUsd(b.val)}
                              style={{ fontSize: "0.6875rem", padding: "0.2rem 0.45rem" }}
                            >
                              {b.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Reset Frequency */}
                      <div>
                        <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                          Budget Reset Frequency
                        </label>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem" }}>
                          {[
                            { id: "monthly", label: "Monthly" },
                            { id: "weekly", label: "Weekly" },
                            { id: "daily", label: "Daily" },
                            { id: "total", label: "Lifetime" },
                          ].map((p) => (
                            <button
                              key={p.id}
                              type="button"
                              className={`btn btn-xs ${budgetResetPeriod === p.id ? "btn-primary" : "btn-secondary"}`}
                              onClick={() => setBudgetResetPeriod(p.id)}
                              style={{ fontSize: "0.6875rem", padding: "0.35rem 0.4rem" }}
                            >
                              {p.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Exceeded Action */}
                      <div>
                        <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                          Action When Budget Cap Reached
                        </label>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                          <div
                            onClick={() => setBudgetExceededAction("hard_cap")}
                            style={{
                              padding: "0.55rem 0.75rem",
                              borderRadius: "var(--radius-sm)",
                              backgroundColor: budgetExceededAction === "hard_cap" ? "var(--bg-elevated)" : "var(--bg-surface)",
                              border: budgetExceededAction === "hard_cap" ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                              cursor: "pointer",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.2rem",
                              transition: "all 0.12s ease",
                            }}
                          >
                            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: budgetExceededAction === "hard_cap" ? "var(--accent)" : "var(--text-primary)" }}>
                              Hard Cap (429)
                            </span>
                            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                              Immediately reject incoming requests with HTTP 429 budget cap error
                            </span>
                          </div>

                          <div
                            onClick={() => setBudgetExceededAction("fallback_to_free")}
                            style={{
                              padding: "0.55rem 0.75rem",
                              borderRadius: "var(--radius-sm)",
                              backgroundColor: budgetExceededAction === "fallback_to_free" ? "var(--bg-elevated)" : "var(--bg-surface)",
                              border: budgetExceededAction === "fallback_to_free" ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                              cursor: "pointer",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.2rem",
                              transition: "all 0.12s ease",
                            }}
                          >
                            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: budgetExceededAction === "fallback_to_free" ? "var(--accent)" : "var(--text-primary)" }}>
                              Fallback to Free
                            </span>
                            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                              Gracefully divert requests to free-tier model instances
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Velocity Limit */}
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                            Spend Velocity Limit ($/min)
                          </label>
                          <ShieldAlert size={13} style={{ color: "var(--warning)" }} />
                        </div>
                        <input
                          type="number"
                          step="0.5"
                          min="0"
                          className="form-input font-mono"
                          placeholder="e.g. 2.00 (leave blank to disable)"
                          value={spendVelocityLimitUsd}
                          onChange={(e) => setSpendVelocityLimitUsd(e.target.value)}
                          style={{ fontSize: "0.75rem", padding: "0.4rem 0.6rem", marginTop: "0.3rem" }}
                        />
                        <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", marginTop: "0.2rem", display: "block" }}>
                          Trips circuit breaker to reject requests if spending rate surpasses this threshold in a rolling 60-second window.
                        </span>
                      </div>
                    </div>

                    {/* Footer */}
                    <div
                      style={{
                        borderTop: "1px solid var(--border-subtle)",
                        padding: "0.875rem 1.25rem",
                        display: "flex",
                        justifyContent: "flex-end",
                        gap: "0.5rem",
                        backgroundColor: "var(--bg-elevated)",
                      }}
                    >
                      <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} disabled={isSaving}>
                        Cancel
                      </button>
                      <button type="submit" className="btn btn-primary btn-sm flex items-center gap-1" disabled={isSaving}>
                        {isSaving ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                        <span>{isSaving ? "Saving..." : "Save Budget"}</span>
                      </button>
                    </div>
                  </form>
                </motion.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
