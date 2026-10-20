import { useState, useMemo } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "motion/react";
import { Shield, X, Search, CheckCircle2, Lock } from "lucide-react";

interface ModelScopeInspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: any | null;
  workers: any[];
  modelGroups?: any[];
}

export function ModelScopeInspectorModal({
  isOpen,
  onClose,
  apiKey,
  workers,
  modelGroups = [],
}: ModelScopeInspectorModalProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const mode = apiKey?.worker_selection_mode || "AUTO";
  const allowedIds: string[] = apiKey?.allowed_worker_ids || [];
  const specificWorkerId: string | null = apiKey?.specific_worker_id || null;
  const allowedModelGroups: string[] = apiKey?.allowed_model_groups || [];

  // Filter allowed workers
  const allowedWorkers = useMemo(() => {
    if (!apiKey) return [];
    if (mode === "AUTO") {
      return workers;
    }
    if (mode === "SPECIFIC_WORKER") {
      return workers.filter((w) => w.id === specificWorkerId);
    }
    if (mode === "WORKER_POOL") {
      const set = new Set(allowedIds);
      return workers.filter((w) => set.has(w.id));
    }
    if (mode === "MODEL_GROUPS") {
      const allowedGroupsSet = new Set(allowedModelGroups);
      const matchedModelPatterns = new Set<string>();
      modelGroups.forEach((g) => {
        if (allowedGroupsSet.has(g.id)) {
          (g.models || []).forEach((m: string) => {
            matchedModelPatterns.add(m.toLowerCase());
            matchedModelPatterns.add((m.split("/").pop() || m).toLowerCase());
          });
        }
      });
      return workers.filter((w) => {
        const wModel = (w.model || "").toLowerCase();
        const wBare = (wModel.split("/").pop() || wModel);
        return matchedModelPatterns.has(wModel) || matchedModelPatterns.has(wBare);
      });
    }
    return [];
  }, [apiKey, mode, allowedIds, specificWorkerId, allowedModelGroups, modelGroups, workers]);

  // Search filtered workers
  const displayedWorkers = useMemo(() => {
    if (!searchQuery.trim()) return allowedWorkers;
    const q = searchQuery.toLowerCase().trim();
    return allowedWorkers.filter((w) =>
      (w.name || "").toLowerCase().includes(q) ||
      (w.model || "").toLowerCase().includes(q) ||
      (w.provider || "").toLowerCase().includes(q)
    );
  }, [allowedWorkers, searchQuery]);

  const uniqueProviders = useMemo(() => {
    return Array.from(new Set(allowedWorkers.map((w) => (w.provider || "gateway").toLowerCase())));
  }, [allowedWorkers]);

  if (!apiKey) return null;

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
                transition={{ duration: 0.15 }}
                className="modal-overlay"
                style={{ zIndex: 1000 }}
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
                  transition={{ type: "spring", damping: 25, stiffness: 350 }}
                  className="modal-content"
                  style={{
                    maxWidth: "560px",
                    width: "100%",
                    pointerEvents: "auto",
                    boxShadow: "0 20px 48px rgba(0, 0, 0, 0.6)",
                    border: "1px solid var(--border-strong)",
                  }}
                >
                  {/* Header */}
                  <div className="modal-header">
                    <div className="modal-title" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <Shield size={16} style={{ color: "var(--accent)" }} />
                      <span style={{ fontWeight: 600 }}>Model Access Scope Inspector</span>
                    </div>
                    <Dialog.Close asChild>
                      <button className="btn btn-ghost btn-sm" aria-label="Close">
                        <X size={14} />
                      </button>
                    </Dialog.Close>
                  </div>

                  {/* Body */}
                  <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {/* Key Details Card */}
                    <div
                      style={{
                        padding: "0.75rem",
                        borderRadius: "var(--radius-sm)",
                        backgroundColor: "var(--bg-elevated)",
                        border: "1px solid var(--border-default)",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.375rem",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.8125rem" }}>
                          {apiKey.name}
                        </span>
                        <span
                          className={`status-pill ${
                            mode === "MODEL_GROUPS"
                              ? "info"
                              : mode === "WORKER_POOL"
                              ? ""
                              : mode === "SPECIFIC_WORKER"
                              ? "warning"
                              : "success"
                          }`}
                          style={{
                            fontSize: "0.6875rem",
                            backgroundColor: mode === "MODEL_GROUPS" ? "var(--accent-muted)" : undefined,
                            color: mode === "MODEL_GROUPS" ? "var(--accent)" : undefined,
                            border: mode === "MODEL_GROUPS" ? "1px solid var(--accent-border)" : undefined,
                          }}
                        >
                          {mode === "MODEL_GROUPS"
                            ? `Virtual Tiers (${allowedModelGroups.length} assigned)`
                            : mode === "WORKER_POOL"
                            ? "Custom Pool"
                            : mode === "SPECIFIC_WORKER"
                            ? "Pinned Single Target"
                            : "Full Autonomous Access (AUTO)"}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: "1rem", fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                        <span>Prefix: <code className="font-mono text-secondary">{apiKey.masked_key || apiKey.prefix}</code></span>
                        <span>Policy: <span style={{ textTransform: "capitalize", color: "var(--text-secondary)" }}>{apiKey.routing_policy || "balanced"}</span></span>
                      </div>
                    </div>

                    {/* Stats & Search */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        {mode === "AUTO" ? (
                          <span>Permitted for <strong>all {workers.length}</strong> active gateway models</span>
                        ) : (
                          <span>
                            Permitted for <strong>{allowedWorkers.length}</strong> of {workers.length} models across {uniqueProviders.length} providers
                          </span>
                        )}
                      </div>

                      {allowedWorkers.length > 5 && (
                        <div style={{ position: "relative", width: "180px" }}>
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
                            placeholder="Filter models..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            style={{ paddingLeft: "1.75rem", fontSize: "0.6875rem", height: "28px" }}
                          />
                        </div>
                      )}
                    </div>

                    {/* Workers List */}
                    <div
                      style={{
                        maxHeight: "240px",
                        overflowY: "auto",
                        border: "1px solid var(--border-default)",
                        borderRadius: "var(--radius-sm)",
                        backgroundColor: "var(--bg-canvas)",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.25rem",
                        padding: "0.375rem",
                      }}
                    >
                      {displayedWorkers.length === 0 ? (
                        <div style={{ textAlign: "center", padding: "1.5rem", color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                          {searchQuery ? "No models match your search query." : "No models configured for this key."}
                        </div>
                      ) : (
                        displayedWorkers.map((w) => (
                          <div
                            key={w.id}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              padding: "0.4rem 0.625rem",
                              borderRadius: "var(--radius-xs)",
                              backgroundColor: "var(--bg-surface)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <CheckCircle2 size={13} style={{ color: "var(--success)" }} />
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <span style={{ fontWeight: 600, fontSize: "0.75rem", color: "var(--text-primary)" }}>
                                  {w.name}
                                </span>
                                <span className="font-mono text-tertiary" style={{ fontSize: "0.625rem" }}>
                                  {w.provider_model_name || w.model}
                                </span>
                              </div>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                              <span
                                className="font-mono"
                                style={{
                                  fontSize: "0.625rem",
                                  padding: "0.1rem 0.35rem",
                                  borderRadius: "var(--radius-xs)",
                                  backgroundColor: "var(--bg-elevated)",
                                  border: "1px solid var(--border-default)",
                                  textTransform: "uppercase",
                                }}
                              >
                                {w.provider || "llm"}
                              </span>
                              <span
                                className={`status-pill ${w.is_healthy ? "" : "warning"}`}
                                style={{ fontSize: "0.5625rem", padding: "0.1rem 0.3rem" }}
                              >
                                {w.is_healthy ? "ONLINE" : "DEGRADED"}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Enforcement Security Note */}
                    <div
                      style={{
                        padding: "0.625rem 0.75rem",
                        borderRadius: "var(--radius-sm)",
                        backgroundColor: "rgba(59, 130, 246, 0.08)",
                        border: "1px solid rgba(59, 130, 246, 0.2)",
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "0.5rem",
                        fontSize: "0.6875rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.4,
                      }}
                    >
                      <Lock size={13} style={{ color: "var(--accent)", marginTop: "0.1rem", flexShrink: 0 }} />
                      <span>
                        <strong>Enforced at Gateway Boundary:</strong> Any request submitted with this key targeting an unpermitted model or virtual group without allowed members will be rejected with <code>HTTP 403 Forbidden (permission_denied)</code>.
                      </span>
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="modal-footer">
                    <Dialog.Close asChild>
                      <button className="btn btn-secondary btn-sm">Close</button>
                    </Dialog.Close>
                  </div>
                </motion.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
