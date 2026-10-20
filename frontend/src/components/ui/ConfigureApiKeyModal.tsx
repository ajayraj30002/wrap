import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "motion/react";
import {
  X,
  Sliders,
  Check,
  Search,
  Layers,
  Cpu,
  Globe,
  Pin,
  RefreshCw,
  CheckCircle2,
  DollarSign,
  ExternalLink,
} from "lucide-react";
import { apiClient } from "../../lib/apiClient";
import { useToast } from "../../contexts/ToastContext";

export interface GatewayKeyItem {
  id: string;
  name: string;
  masked_key: string;
  enabled: boolean;
  created_at: string;
  last_used_at?: string;
  revoked_at?: string;
  status: string;
  worker_selection_mode: "AUTO" | "MODEL_GROUPS" | "WORKER_POOL" | "SPECIFIC_WORKER" | string;
  routing_policy: string;
  specific_worker_id?: string | null;
  allowed_worker_ids?: string[];
  allowed_model_groups?: string[];
  rate_limit_rpm?: number;
  max_budget_usd?: number | null;
  spend_usd?: number;
  value_saved_usd?: number;
  budget_reset_period?: "daily" | "weekly" | "monthly" | "total" | string | null;
  budget_exceeded_action?: "hard_cap" | "fallback_to_free" | string;
  spend_velocity_limit_usd?: number | null;
  spend_velocity_window_sec?: number;
}

interface ConfigureApiKeyModalProps {
  apiKey: GatewayKeyItem | null;
  isOpen: boolean;
  onClose: () => void;
  onKeyUpdated: () => void;
  workers: any[];
  modelGroups: any[];
}

export function ConfigureApiKeyModal({
  apiKey,
  isOpen,
  onClose,
  onKeyUpdated,
  workers,
  modelGroups,
}: ConfigureApiKeyModalProps) {
  const { toast } = useToast();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState<"AUTO" | "MODEL_GROUPS" | "WORKER_POOL" | "SPECIFIC_WORKER">("AUTO");
  const [routingPolicy, setRoutingPolicy] = useState("balanced");
  const [rateLimitRpm, setRateLimitRpm] = useState(120);
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [selectedWorkerIds, setSelectedWorkerIds] = useState<string[]>([]);
  const [specificWorkerId, setSpecificWorkerId] = useState<string>("");
  const [checklistSearch, setChecklistSearch] = useState("");
  const [checklistProvider, setChecklistProvider] = useState("ALL");
  const [isSaving, setIsSaving] = useState(false);

  // Sync state whenever apiKey prop changes
  useEffect(() => {
    if (apiKey) {
      setName(apiKey.name || "");
      setEnabled(apiKey.enabled ?? true);
      setMode((apiKey.worker_selection_mode as any) || "AUTO");
      setRoutingPolicy(apiKey.routing_policy || "balanced");
      setRateLimitRpm(apiKey.rate_limit_rpm || 120);
      setSelectedGroups(apiKey.allowed_model_groups || []);
      setSelectedWorkerIds(apiKey.allowed_worker_ids || []);
      setSpecificWorkerId(apiKey.specific_worker_id || "");
    }
  }, [apiKey]);

  if (!apiKey) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast({ title: "Name Required", description: "API Key name cannot be empty", type: "warning" });
      return;
    }

    if (mode === "MODEL_GROUPS" && selectedGroups.length === 0) {
      toast({
        title: "Virtual Tiers Required",
        description: "Please select at least one Virtual Tier for this key.",
        type: "warning",
      });
      return;
    }

    if (mode === "WORKER_POOL" && selectedWorkerIds.length === 0) {
      toast({
        title: "Models Required",
        description: "Please checklist at least one model for this worker pool.",
        type: "warning",
      });
      return;
    }

    if (mode === "SPECIFIC_WORKER" && !specificWorkerId) {
      toast({
        title: "Worker Required",
        description: "Please select a specific target worker to pin.",
        type: "warning",
      });
      return;
    }

    setIsSaving(true);
    try {
      const payload: any = {
        name: name.trim(),
        enabled,
        worker_selection_mode: mode,
        routing_policy: routingPolicy,
        rate_limit_rpm: Number(rateLimitRpm) || 120,
      };

      if (mode === "MODEL_GROUPS") {
        payload.allowed_model_groups = selectedGroups;
        payload.allowed_worker_ids = null;
        payload.specific_worker_id = null;
      } else if (mode === "WORKER_POOL") {
        payload.allowed_worker_ids = selectedWorkerIds;
        payload.allowed_model_groups = null;
        payload.specific_worker_id = null;
      } else if (mode === "SPECIFIC_WORKER") {
        payload.specific_worker_id = specificWorkerId;
        payload.allowed_worker_ids = null;
        payload.allowed_model_groups = null;
      } else {
        payload.allowed_worker_ids = null;
        payload.allowed_model_groups = null;
        payload.specific_worker_id = null;
      }

      await apiClient.patch(`/api/apikeys/${apiKey.id}`, payload);
      toast({
        title: "API Key Updated",
        description: `Successfully configured permissions, rate limit & routing for ${name}`,
        type: "success",
      });
      onKeyUpdated();
      onClose();
    } catch (err: any) {
      toast({
        title: "Update Failed",
        description: err.data?.detail || err.message || "Failed to update API key",
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const toggleGroup = (groupId: string) => {
    setSelectedGroups((prev) =>
      prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]
    );
  };

  const availableProviders = Array.from(new Set(workers.map((w) => w.provider).filter(Boolean)));
  const filteredWorkers = workers.filter((w) => {
    if (checklistProvider !== "ALL" && (w.provider || "").toLowerCase() !== checklistProvider.toLowerCase()) {
      return false;
    }
    if (checklistSearch.trim()) {
      const q = checklistSearch.toLowerCase().trim();
      return (
        (w.name || "").toLowerCase().includes(q) ||
        (w.model || "").toLowerCase().includes(q) ||
        (w.provider || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

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
                    maxWidth: "700px",
                    maxHeight: "88vh",
                    backgroundColor: "var(--bg-surface)",
                    border: "1px solid var(--border-default)",
                    borderRadius: "var(--radius-lg)",
                    boxShadow: "0 20px 48px rgba(0, 0, 0, 0.6)",
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
                      <Sliders size={17} style={{ color: "var(--accent)" }} />
                      <Dialog.Title
                        style={{
                          margin: 0,
                          fontSize: "0.9375rem",
                          fontWeight: 600,
                          color: "var(--text-primary)",
                        }}
                      >
                        Configure Gateway API Key
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
                        {apiKey.masked_key}
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

                  {/* Form Body */}
                  <form
                    onSubmit={handleSave}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      flex: 1,
                      minHeight: 0,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        flex: 1,
                        minHeight: 0,
                        overflowY: "auto",
                        padding: "1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "1.25rem",
                      }}
                    >
                      {/* General Row: Key Name & Active Switch */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "1rem", alignItems: "end" }}>
                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                            Key Name / Application Identifier
                          </label>
                          <input
                            type="text"
                            className="form-input"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Cursor Pro, CLI Agent, Production Microservice..."
                            required
                            style={{ fontSize: "0.8125rem" }}
                          />
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                            Status
                          </label>
                          <button
                            type="button"
                            onClick={() => setEnabled(!enabled)}
                            style={{
                              height: "36px",
                              padding: "0 0.75rem",
                              borderRadius: "var(--radius-md)",
                              fontSize: "0.75rem",
                              fontWeight: 600,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.4rem",
                              cursor: "pointer",
                              backgroundColor: enabled ? "var(--success-muted)" : "var(--error-muted)",
                              color: enabled ? "var(--success)" : "var(--error)",
                              border: `1px solid ${enabled ? "var(--success-border)" : "var(--error-border)"}`,
                              transition: "all 0.15s ease",
                            }}
                          >
                            <span
                              style={{
                                width: "7px",
                                height: "7px",
                                borderRadius: "50%",
                                backgroundColor: enabled ? "var(--success)" : "var(--error)",
                              }}
                            />
                            <span>{enabled ? "ACTIVE" : "DISABLED"}</span>
                          </button>
                        </div>
                      </div>

                      {/* Routing Policy Selector */}
                      <div className="form-group" style={{ margin: 0 }}>
                        <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                          Autonomous Routing Policy
                        </label>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.5rem" }}>
                          {[
                            { id: "balanced", label: "Balanced", desc: "Multi-factor throughput & latency" },
                            { id: "quality_first", label: "Quality First", desc: "Frontier reasoning & 70B+ models" },
                            { id: "latency_optimized", label: "Lowest Latency", desc: "Fastest response LPU/hardware" },
                            { id: "cost_optimized", label: "Cost Optimized", desc: "Free tier headroom & economy" },
                          ].map((pol) => {
                            const isSelected = routingPolicy === pol.id;
                            return (
                              <div
                                key={pol.id}
                                onClick={() => setRoutingPolicy(pol.id)}
                                style={{
                                  padding: "0.5rem 0.65rem",
                                  borderRadius: "var(--radius-sm)",
                                  backgroundColor: isSelected ? "var(--bg-elevated)" : "var(--bg-canvas)",
                                  border: isSelected ? "1px solid var(--accent)" : "1px solid var(--border-subtle)",
                                  cursor: "pointer",
                                  display: "flex",
                                  flexDirection: "column",
                                  gap: "0.2rem",
                                  transition: "all 0.12s ease",
                                }}
                              >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                  <span style={{ fontSize: "0.75rem", fontWeight: 600, color: isSelected ? "var(--accent)" : "var(--text-primary)" }}>
                                    {pol.label}
                                  </span>
                                  {isSelected && <Check size={11} style={{ color: "var(--accent)" }} />}
                                </div>
                                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", lineHeight: 1.25 }}>
                                  {pol.desc}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* MODEL ACCESS SCOPE — 4 SECTIONS */}
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                            Model Access Scope & Worker Permissions
                          </label>
                          <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                            Enforced at gateway scheduler boundary
                          </span>
                        </div>

                        {/* 4 Interactive Mode Cards */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem" }}>
                          {[
                            {
                              id: "AUTO",
                              icon: <Globe size={14} />,
                              title: "All Models",
                              desc: "Full cluster access & autonomous DAG routing",
                            },
                            {
                              id: "MODEL_GROUPS",
                              icon: <Layers size={14} />,
                              title: "Virtual Tiers",
                              desc: "Scoped to specific multi-model fallback cascades",
                            },
                            {
                              id: "WORKER_POOL",
                              icon: <Cpu size={14} />,
                              title: "Custom Pool",
                              desc: "Fine-grained checklist of individual models",
                            },
                            {
                              id: "SPECIFIC_WORKER",
                              icon: <Pin size={14} />,
                              title: "Pinned Worker",
                              desc: "Hard-pinned dedicated hardware instance",
                            },
                          ].map((m) => {
                            const isCurrent = mode === m.id;
                            return (
                              <button
                                key={m.id}
                                type="button"
                                onClick={() => setMode(m.id as any)}
                                style={{
                                  padding: "0.65rem 0.5rem",
                                  borderRadius: "var(--radius-md)",
                                  backgroundColor: isCurrent ? "var(--bg-elevated)" : "var(--bg-canvas)",
                                  border: isCurrent ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                                  cursor: "pointer",
                                  display: "flex",
                                  flexDirection: "column",
                                  alignItems: "center",
                                  textAlign: "center",
                                  gap: "0.3rem",
                                  transition: "all 0.15s ease",
                                }}
                              >
                                <span style={{ color: isCurrent ? "var(--accent)" : "var(--text-secondary)" }}>
                                  {m.icon}
                                </span>
                                <span
                                  style={{
                                    fontSize: "0.75rem",
                                    fontWeight: 600,
                                    color: isCurrent ? "var(--text-primary)" : "var(--text-secondary)",
                                  }}
                                >
                                  {m.title}
                                </span>
                                <span
                                  style={{
                                    fontSize: "0.5625rem",
                                    color: "var(--text-tertiary)",
                                    lineHeight: 1.25,
                                  }}
                                >
                                  {m.desc}
                                </span>
                              </button>
                            );
                          })}
                        </div>

                        {/* MODE 1: AUTO */}
                        {mode === "AUTO" && (
                          <div
                            style={{
                              backgroundColor: "var(--bg-elevated)",
                              border: "1px dashed var(--border-subtle)",
                              borderRadius: "var(--radius-sm)",
                              padding: "0.75rem",
                              display: "flex",
                              alignItems: "center",
                              gap: "0.5rem",
                              fontSize: "0.75rem",
                              color: "var(--text-secondary)",
                            }}
                          >
                            <CheckCircle2 size={15} style={{ color: "var(--success)", flexShrink: 0 }} />
                            <span>
                              <strong>Unrestricted Scope:</strong> Client requests bearing this key may target any registered provider model, virtual tier, or use autonomous model selection (<code className="font-mono">model: &quot;auto&quot;</code>).
                            </span>
                          </div>
                        )}

                        {/* MODE 2: VIRTUAL TIERS */}
                        {mode === "MODEL_GROUPS" && (
                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-default)",
                              borderRadius: "var(--radius-md)",
                              padding: "0.75rem",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.625rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                                Select Permitted Virtual Tiers ({selectedGroups.length} selected)
                              </span>
                              <div style={{ display: "flex", gap: "0.35rem" }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setSelectedGroups(modelGroups.map((g) => g.id))}
                                >
                                  Select All
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setSelectedGroups([])}
                                >
                                  Clear
                                </button>
                              </div>
                            </div>

                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                              {modelGroups.map((group) => {
                                const isChecked = selectedGroups.includes(group.id);
                                return (
                                  <div
                                    key={group.id}
                                    onClick={() => toggleGroup(group.id)}
                                    style={{
                                      padding: "0.6rem 0.75rem",
                                      borderRadius: "var(--radius-sm)",
                                      backgroundColor: isChecked ? "var(--bg-elevated)" : "var(--bg-surface)",
                                      border: isChecked ? "1.5px solid var(--accent)" : "1px solid var(--border-subtle)",
                                      cursor: "pointer",
                                      display: "flex",
                                      flexDirection: "column",
                                      gap: "0.35rem",
                                      transition: "all 0.12s ease",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                        <input
                                          type="checkbox"
                                          checked={isChecked}
                                          onChange={() => {}}
                                          style={{ accentColor: "var(--accent)", cursor: "pointer" }}
                                        />
                                        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                          {group.name}
                                        </span>
                                      </div>
                                      <span
                                        className="font-mono text-tertiary"
                                        style={{
                                          fontSize: "0.5625rem",
                                          backgroundColor: "var(--bg-subtle)",
                                          padding: "0.1rem 0.3rem",
                                          borderRadius: "2px",
                                        }}
                                      >
                                        {group.routing_strategy}
                                      </span>
                                    </div>
                                    <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", lineHeight: 1.3 }}>
                                      {group.description || `${group.models?.length || 0} models participating`}
                                    </span>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.2rem", marginTop: "0.15rem" }}>
                                      {group.models?.slice(0, 3).map((m: string) => (
                                        <span
                                          key={m}
                                          className="font-mono"
                                          style={{
                                            fontSize: "0.5625rem",
                                            color: "var(--text-secondary)",
                                            backgroundColor: "var(--bg-elevated)",
                                            padding: "0.05rem 0.25rem",
                                            borderRadius: "2px",
                                            border: "1px solid var(--border-subtle)",
                                          }}
                                        >
                                          {m.split("/").pop()}
                                        </span>
                                      ))}
                                      {(group.models?.length || 0) > 3 && (
                                        <span style={{ fontSize: "0.5625rem", color: "var(--text-tertiary)" }}>
                                          +{group.models.length - 3} more
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* MODE 3: CUSTOM MODEL POOL */}
                        {mode === "WORKER_POOL" && (
                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-default)",
                              borderRadius: "var(--radius-md)",
                              padding: "0.75rem",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.5rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                                Custom Model Checklist ({selectedWorkerIds.length} of {workers.length} selected)
                              </span>
                              <div style={{ display: "flex", gap: "0.35rem" }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setSelectedWorkerIds(workers.map((w) => w.id))}
                                >
                                  Select All
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setSelectedWorkerIds([])}
                                >
                                  Clear
                                </button>
                              </div>
                            </div>

                            {/* Search & Provider Filter */}
                            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                              <div style={{ position: "relative", flex: 1, minWidth: "140px" }}>
                                <Search
                                  size={12}
                                  style={{
                                    position: "absolute",
                                    left: "0.5rem",
                                    top: "50%",
                                    transform: "translateY(-50%)",
                                    color: "var(--text-tertiary)",
                                  }}
                                />
                                <input
                                  type="text"
                                  className="form-input"
                                  placeholder="Search models..."
                                  value={checklistSearch}
                                  onChange={(e) => setChecklistSearch(e.target.value)}
                                  style={{ paddingLeft: "1.75rem", fontSize: "0.6875rem", height: "26px" }}
                                />
                              </div>

                              <div className="filter-btn-group" style={{ margin: 0 }}>
                                <button
                                  type="button"
                                  className={`filter-btn btn-xs ${checklistProvider === "ALL" ? "active" : ""}`}
                                  onClick={() => setChecklistProvider("ALL")}
                                  style={{ padding: "0.15rem 0.4rem", fontSize: "0.625rem" }}
                                >
                                  All ({workers.length})
                                </button>
                                {availableProviders.map((p) => (
                                  <button
                                    key={p}
                                    type="button"
                                    className={`filter-btn btn-xs ${checklistProvider.toLowerCase() === p.toLowerCase() ? "active" : ""}`}
                                    onClick={() => setChecklistProvider(p)}
                                    style={{ padding: "0.15rem 0.4rem", fontSize: "0.625rem", textTransform: "capitalize" }}
                                  >
                                    {p}
                                  </button>
                                ))}
                              </div>
                            </div>

                            {/* Tier Presets */}
                            {modelGroups.length > 0 && (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", alignSelf: "center" }}>
                                  Add Tier:
                                </span>
                                {modelGroups.map((g) => {
                                  const groupWorkerIds = workers
                                    .filter((w) =>
                                      g.models?.some((m: string) => {
                                        const mBare = m.split("/").pop() || m;
                                        const wBare = (w.model || "").split("/").pop() || w.model;
                                        return m === w.model || mBare === wBare;
                                      })
                                    )
                                    .map((w) => w.id);

                                  return (
                                    <button
                                      key={g.id}
                                      type="button"
                                      className="btn btn-ghost btn-xs"
                                      style={{
                                        fontSize: "0.625rem",
                                        padding: "0.1rem 0.4rem",
                                        borderRadius: "var(--radius-xs)",
                                        border: "1px solid var(--border-default)",
                                      }}
                                      onClick={() => {
                                        setSelectedWorkerIds((prev) => {
                                          const next = new Set(prev);
                                          groupWorkerIds.forEach((id: string) => next.add(id));
                                          return Array.from(next);
                                        });
                                      }}
                                    >
                                      + {g.name} ({groupWorkerIds.length})
                                    </button>
                                  );
                                })}
                              </div>
                            )}

                            {/* Checklist View */}
                            <div
                              style={{
                                maxHeight: "160px",
                                overflowY: "auto",
                                border: "1px solid var(--border-default)",
                                borderRadius: "var(--radius-sm)",
                                padding: "0.35rem",
                                backgroundColor: "var(--bg-surface)",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.25rem",
                              }}
                            >
                              {filteredWorkers.map((w) => {
                                const isChecked = selectedWorkerIds.includes(w.id);
                                return (
                                  <label
                                    key={w.id}
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      gap: "0.5rem",
                                      padding: "0.3rem 0.45rem",
                                      borderRadius: "var(--radius-xs)",
                                      backgroundColor: isChecked ? "var(--bg-elevated)" : "transparent",
                                      cursor: "pointer",
                                      fontSize: "0.75rem",
                                      border: isChecked ? "1px solid var(--border-focus)" : "1px solid transparent",
                                    }}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={(e) => {
                                        if (e.target.checked) {
                                          setSelectedWorkerIds((prev) => [...prev, w.id]);
                                        } else {
                                          setSelectedWorkerIds((prev) => prev.filter((id) => id !== w.id));
                                        }
                                      }}
                                      style={{ accentColor: "var(--accent)", cursor: "pointer" }}
                                    />
                                    <div style={{ flex: 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                        <span className="font-mono text-primary" style={{ fontWeight: 600 }}>
                                          {w.model}
                                        </span>
                                        <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                                          {w.provider}
                                        </span>
                                      </div>
                                      <span
                                        className="font-mono"
                                        style={{
                                          fontSize: "0.5625rem",
                                          padding: "0.05rem 0.3rem",
                                          borderRadius: "2px",
                                          backgroundColor: "var(--bg-subtle)",
                                          color: "var(--text-secondary)",
                                        }}
                                      >
                                        {w.name}
                                      </span>
                                    </div>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* MODE 4: SPECIFIC WORKER */}
                        {mode === "SPECIFIC_WORKER" && (
                          <div
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              border: "1px solid var(--border-default)",
                              borderRadius: "var(--radius-md)",
                              padding: "0.75rem",
                            }}
                          >
                            <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                              Select Pinned Computational Worker
                            </label>
                            <select
                              className="form-select font-mono"
                              value={specificWorkerId}
                              onChange={(e) => setSpecificWorkerId(e.target.value)}
                              required
                              style={{ fontSize: "0.75rem" }}
                            >
                              <option value="">-- Choose Target Worker --</option>
                              {workers.map((w) => (
                                <option key={w.id} value={w.id}>
                                  {w.model} ({w.provider}) — {w.name}
                                </option>
                              ))}
                            </select>
                            <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)", marginTop: "0.25rem", display: "block" }}>
                              All requests using this key will be strictly bound to this specific worker instance.
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Rate Limiting (Sliding Window RPM) */}
                      <div className="form-group" style={{ margin: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, margin: 0 }}>
                            Rate Limiting (Sliding Window RPM)
                          </label>
                          <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
                            {rateLimitRpm} requests / minute
                          </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginTop: "0.35rem" }}>
                          <input
                            type="number"
                            min="10"
                            max="10000"
                            step="10"
                            className="form-input font-mono"
                            value={rateLimitRpm}
                            onChange={(e) => setRateLimitRpm(Number(e.target.value) || 120)}
                            style={{ width: "110px", fontSize: "0.75rem" }}
                          />
                          <div className="filter-btn-group" style={{ flex: 1, margin: 0 }}>
                            {[60, 120, 300, 1000].map((preset) => (
                              <button
                                key={preset}
                                type="button"
                                className={`filter-btn ${rateLimitRpm === preset ? "active" : ""}`}
                                onClick={() => setRateLimitRpm(preset)}
                                style={{ fontSize: "0.6875rem", padding: "0.2rem 0.5rem" }}
                              >
                                {preset} RPM
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Informative Budget & Spend Governance Banner */}
                      <div
                        style={{
                          borderRadius: "var(--radius-md)",
                          border: "1px solid var(--border-subtle)",
                          backgroundColor: "var(--bg-canvas)",
                          padding: "0.75rem 1rem",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "0.75rem",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <DollarSign size={15} style={{ color: "var(--accent)", flexShrink: 0 }} />
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              Financial Budget & Spend Governance
                            </span>
                            <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                              {apiKey.max_budget_usd != null
                                ? `Hard spend cap: $${Number(apiKey.max_budget_usd).toFixed(2)} (${apiKey.budget_reset_period || "Monthly"}) · Governed in Budgets & Spend`
                                : "Uncapped spend · Configurable in the dedicated Budgets & Spend sidebar tab"}
                            </span>
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-secondary btn-xs flex items-center gap-1"
                          onClick={() => {
                            onClose();
                            navigate("/settings/budgets");
                          }}
                          style={{ fontSize: "0.6875rem", padding: "0.25rem 0.55rem", flexShrink: 0 }}
                        >
                          <span>Open Budgets & Spend</span>
                          <ExternalLink size={10} />
                        </button>
                      </div>
                    </div>

                    {/* Footer Actions */}
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
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={onClose}
                        disabled={isSaving}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm flex items-center gap-1"
                        disabled={isSaving}
                      >
                        {isSaving ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                        <span>{isSaving ? "Saving..." : "Save Configuration"}</span>
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
