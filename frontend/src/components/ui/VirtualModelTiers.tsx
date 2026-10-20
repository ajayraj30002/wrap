import { useState, useMemo } from "react";
import {
  Layers,
  Zap,
  Sparkles,
  Sliders,
  Code2,
  Copy,
  Check,
  Play,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertCircle,
  Terminal,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import * as Dialog from "@radix-ui/react-dialog";
import { apiClient } from "../../lib/apiClient";
import { useToast } from "../../contexts/ToastContext";

interface VirtualModelTiersProps {
  modelGroups: any[];
  workers: any[];
  onRefresh: () => void;
  loading: boolean;
}

export function VirtualModelTiers({
  modelGroups,
  workers,
  onRefresh,
  loading,
}: VirtualModelTiersProps) {
  const { toast } = useToast();
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [policyFilter, setPolicyFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Test Runner State
  const [testModalGroup, setTestModalGroup] = useState<any | null>(null);
  const [testPrompt, setTestPrompt] = useState("Summarize the operational status of the cluster in one concise sentence.");
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<any | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast({ title: "Model ID Copied", description: `Copied '${text}' to clipboard`, type: "success" });
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getPolicyIcon = (policy: string) => {
    switch (policy) {
      case "latency_optimized":
        return <Zap size={12} style={{ color: "#38bdf8" }} />;
      case "quality_first":
        return <Sparkles size={12} style={{ color: "#a855f7" }} />;
      case "balanced":
      default:
        return <Sliders size={12} style={{ color: "#10b981" }} />;
    }
  };

  const getTierIcon = (id: string) => {
    switch (id) {
      case "fast-tier":
        return <Zap size={16} style={{ color: "#38bdf8" }} />;
      case "reasoning-tier":
        return <Sparkles size={16} style={{ color: "#a855f7" }} />;
      case "economy-tier":
        return <Sliders size={16} style={{ color: "#10b981" }} />;
      case "coding-tier":
        return <Code2 size={16} style={{ color: "#f59e0b" }} />;
      default:
        return <Layers size={16} style={{ color: "var(--accent)" }} />;
    }
  };

  // Find workers matching each model in the group
  const isModelOnline = (targetModel: string): { isOnline: boolean; matchingWorkers: any[] } => {
    const cleanTarget = targetModel.toLowerCase().trim();
    const bareTarget = cleanTarget.includes("/") ? cleanTarget.split("/")[1] : cleanTarget;
    const matches = workers.filter((w) => {
      if (!w.enabled) return false;
      const cleanW = (w.model || w.provider_model_name || "").toLowerCase().trim();
      const bareW = cleanW.includes("/") ? cleanW.split("/")[1] : cleanW;
      const provW = w.provider ? `${w.provider.toLowerCase()}/${bareW}` : "";
      return cleanW === cleanTarget || bareW === bareTarget || provW === cleanTarget;
    });
    return { isOnline: matches.length > 0, matchingWorkers: matches };
  };

  const filteredGroups = useMemo(() => {
    return modelGroups.filter((g) => {
      if (policyFilter !== "ALL" && g.default_policy !== policyFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          g.name.toLowerCase().includes(q) ||
          g.id.toLowerCase().includes(q) ||
          g.description.toLowerCase().includes(q) ||
          g.models.some((m: string) => m.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [modelGroups, policyFilter, searchQuery]);

  // Handle live test execution
  const handleExecuteTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testModalGroup) return;
    setIsTesting(true);
    setTestResult(null);

    const startTime = performance.now();
    try {
      // Use internal proxy endpoint or chat completions via apiClient
      const res = await apiClient.post("/v1/chat/completions", {
        model: testModalGroup.id,
        messages: [{ role: "user", content: testPrompt }],
      });
      const durationMs = Math.round(performance.now() - startTime);

      setTestResult({
        success: true,
        durationMs,
        response: res,
        content: res.choices?.[0]?.message?.content || JSON.stringify(res),
        model: res.model || testModalGroup.id,
        usage: res.usage,
      });
    } catch (err: any) {
      const durationMs = Math.round(performance.now() - startTime);
      setTestResult({
        success: false,
        durationMs,
        error: err.data?.detail?.error?.message || err.data?.detail || err.message || "Failed to execute request",
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Top Banner / Explanation */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div>
          <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Virtual Model Groups & Multi-Provider Cascades
          </span>
          <p style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", marginTop: "0.2rem", maxWidth: "700px" }}>
            Route client requests to high-level virtual aliases (e.g. <code>fast-tier</code>, <code>reasoning-tier</code>, <code>economy-tier</code>). WRAP dynamically selects the highest-priority online worker with transparent zero-downtime failover.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button className="btn btn-secondary btn-sm flex items-center gap-1" onClick={onRefresh} disabled={loading} title="Refresh virtual tiers">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh Tiers"}</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div className="filter-btn-group">
          {[
            { id: "ALL", label: `All Tiers (${modelGroups.length})` },
            { id: "latency_optimized", label: "Latency Optimized" },
            { id: "quality_first", label: "Quality First" },
            { id: "balanced", label: "Balanced" },
          ].map((f) => (
            <button
              key={f.id}
              className={`filter-btn ${policyFilter === f.id ? "active" : ""}`}
              onClick={() => setPolicyFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ position: "relative", width: "240px" }}>
          <Search
            size={13}
            style={{
              position: "absolute",
              left: "0.625rem",
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--text-tertiary)",
            }}
          />
          <input
            type="text"
            className="form-input"
            placeholder="Search tiers or models..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: "2rem", fontSize: "0.75rem" }}
          />
        </div>
      </div>

      {/* Grid of Virtual Tier Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(460px, 1fr))",
          gap: "1rem",
        }}
      >
        {filteredGroups.map((group) => {
          const activeWorkersCount = group.active_workers_count || 0;
          const isOnline = activeWorkersCount > 0;

          return (
            <motion.div
              key={group.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
                padding: "1.125rem",
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
                boxShadow: "0 2px 8px rgba(0, 0, 0, 0.25)",
                position: "relative",
              }}
            >
              {/* Card Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "var(--bg-elevated)",
                      border: "1px solid var(--border-subtle)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {getTierIcon(group.id)}
                  </div>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                        {group.name}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginTop: "0.15rem" }}>
                      <code className="font-mono" style={{ fontSize: "0.6875rem", color: "var(--text-secondary)" }}>
                        {group.id}
                      </code>
                      <button
                        className="btn btn-ghost btn-xs"
                        style={{ padding: "0.1rem 0.3rem", height: "auto" }}
                        onClick={() => copyToClipboard(group.id, group.id)}
                        title="Copy Virtual Model ID"
                      >
                        {copiedId === group.id ? (
                          <Check size={11} style={{ color: "var(--success)" }} />
                        ) : (
                          <Copy size={11} style={{ color: "var(--text-tertiary)" }} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.375rem" }}>
                  <span
                    className={`status-pill ${isOnline ? "" : "warning"}`}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      fontSize: "0.625rem",
                    }}
                  >
                    <span className="status-pulse" />
                    <span>{isOnline ? `${activeWorkersCount} WORKERS ONLINE` : "NO ACTIVE WORKERS"}</span>
                  </span>

                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      fontSize: "0.625rem",
                      padding: "0.15rem 0.4rem",
                      borderRadius: "var(--radius-xs)",
                      backgroundColor: "var(--bg-elevated)",
                      border: "1px solid var(--border-subtle)",
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {getPolicyIcon(group.default_policy)}
                    <span>{group.default_policy.replace("_", " ")}</span>
                  </span>
                </div>
              </div>

              {/* Description */}
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.45, margin: 0 }}>
                {group.description}
              </p>

              {/* Fallback Cascade Sequence */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.375rem" }}>
                  <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Fallback Priority Cascade
                  </span>
                  <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                    Top-down priority with LRU load balancing
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                    backgroundColor: "var(--bg-canvas)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-sm)",
                    padding: "0.375rem",
                  }}
                >
                  {group.models.map((modelName: string, index: number) => {
                    const { isOnline: stepOnline, matchingWorkers } = isModelOnline(modelName);

                    return (
                      <div
                        key={modelName}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "0.3rem 0.5rem",
                          borderRadius: "var(--radius-xs)",
                          backgroundColor: stepOnline ? "var(--bg-elevated)" : "transparent",
                          border: stepOnline ? "1px solid var(--border-default)" : "1px solid transparent",
                          fontSize: "0.6875rem",
                          opacity: stepOnline ? 1 : 0.6,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span
                            className="font-mono text-tertiary"
                            style={{
                              fontSize: "0.625rem",
                              width: "16px",
                              height: "16px",
                              borderRadius: "50%",
                              display: "inline-flex",
                              alignItems: "center",
                              justifyContent: "center",
                              backgroundColor: "var(--bg-surface)",
                              border: "1px solid var(--border-default)",
                            }}
                          >
                            {index + 1}
                          </span>
                          <span className="font-mono" style={{ color: stepOnline ? "var(--text-primary)" : "var(--text-tertiary)", fontWeight: stepOnline ? 600 : 400 }}>
                            {modelName}
                          </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                          {stepOnline ? (
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                fontSize: "0.5625rem",
                                color: "var(--success)",
                                backgroundColor: "var(--success-muted)",
                                padding: "0.1rem 0.35rem",
                                borderRadius: "var(--radius-xs)",
                                border: "1px solid var(--success-border)",
                              }}
                            >
                              <CheckCircle2 size={10} />
                              <span>{matchingWorkers.length} {matchingWorkers.length === 1 ? "worker" : "workers"} ready</span>
                            </span>
                          ) : (
                            <span
                              style={{
                                fontSize: "0.5625rem",
                                color: "var(--text-tertiary)",
                                padding: "0.1rem 0.35rem",
                                borderRadius: "var(--radius-xs)",
                              }}
                            >
                              Not connected
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Actions Footer */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingTop: "0.5rem",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    className="btn btn-secondary btn-xs flex items-center gap-1"
                    onClick={() => {
                      setTestModalGroup(group);
                      setTestResult(null);
                    }}
                  >
                    <Play size={11} style={{ color: "var(--accent)" }} />
                    <span>Test Tier</span>
                  </button>

                  <button
                    className="btn btn-ghost btn-xs flex items-center gap-1"
                    onClick={() => copyToClipboard(`curl http://localhost:8000/v1/chat/completions \\\n  -H "Authorization: Bearer $WRAP_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${group.id}", "messages": [{"role": "user", "content": "Hello"}]}'`, `curl-${group.id}`)}
                    title="Copy curl command"
                  >
                    <Terminal size={11} />
                    <span>{copiedId === `curl-${group.id}` ? "Copied" : "Copy cURL"}</span>
                  </button>
                </div>

                <span style={{ fontSize: "0.625rem", color: "var(--text-tertiary)" }}>
                  Resolved at <code>/v1/chat/completions</code>
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Interactive Test Playground Modal */}
      <Dialog.Root open={Boolean(testModalGroup)} onOpenChange={(open) => !open && setTestModalGroup(null)}>
        <AnimatePresence>
          {testModalGroup && (
            <Dialog.Portal forceMount>
              <Dialog.Overlay asChild>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
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
                      maxWidth: "620px",
                      width: "100%",
                      pointerEvents: "auto",
                      boxShadow: "0 24px 60px rgba(0, 0, 0, 0.6)",
                      border: "1px solid var(--border-strong)",
                    }}
                  >
                    <div className="modal-header">
                      <div className="modal-title" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Play size={15} style={{ color: "var(--accent)" }} />
                        <span>Live Test: {testModalGroup.name}</span>
                        <code className="font-mono text-tertiary" style={{ fontSize: "0.6875rem" }}>
                          ({testModalGroup.id})
                        </code>
                      </div>
                      <Dialog.Close asChild>
                        <button className="btn btn-ghost btn-sm" aria-label="Close">
                          <X size={14} />
                        </button>
                      </Dialog.Close>
                    </div>

                    <form onSubmit={handleExecuteTest}>
                      <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                        <div className="form-group">
                          <label className="form-label">Test Prompt</label>
                          <textarea
                            className="form-input font-mono"
                            rows={3}
                            value={testPrompt}
                            onChange={(e) => setTestPrompt(e.target.value)}
                            placeholder="Enter test user message..."
                            required
                          />
                        </div>

                        {/* Test Results Display */}
                        {testResult && (
                          <div
                            style={{
                              padding: "0.875rem",
                              borderRadius: "var(--radius-sm)",
                              backgroundColor: testResult.success ? "var(--bg-canvas)" : "rgba(239, 68, 68, 0.08)",
                              border: testResult.success ? "1px solid var(--border-default)" : "1px solid var(--error-border)",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.5rem",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                {testResult.success ? (
                                  <CheckCircle2 size={14} style={{ color: "var(--success)" }} />
                                ) : (
                                  <AlertCircle size={14} style={{ color: "var(--error)" }} />
                                )}
                                <span style={{ fontWeight: 600, fontSize: "0.75rem", color: testResult.success ? "var(--text-primary)" : "var(--error)" }}>
                                  {testResult.success ? "Inference Completed Successfully" : "Inference Failed"}
                                </span>
                              </div>
                              <span className="font-mono text-secondary" style={{ fontSize: "0.6875rem" }}>
                                {testResult.durationMs}ms
                              </span>
                            </div>

                            {testResult.success ? (
                              <>
                                <div style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", display: "flex", gap: "1rem" }}>
                                  <span>Executed Model: <strong className="font-mono text-primary">{testResult.model}</strong></span>
                                  {testResult.usage && (
                                    <span>Tokens: <strong className="font-mono text-primary">{testResult.usage.total_tokens || testResult.usage.total}</strong></span>
                                  )}
                                </div>
                                <div
                                  style={{
                                    maxHeight: "150px",
                                    overflowY: "auto",
                                    padding: "0.5rem",
                                    borderRadius: "var(--radius-xs)",
                                    backgroundColor: "var(--bg-surface)",
                                    border: "1px solid var(--border-subtle)",
                                    fontSize: "0.75rem",
                                    lineHeight: 1.45,
                                    color: "var(--text-primary)",
                                    whiteSpace: "pre-wrap",
                                  }}
                                >
                                  {testResult.content}
                                </div>
                              </>
                            ) : (
                              <div style={{ fontSize: "0.75rem", color: "var(--error)", lineHeight: 1.4 }}>
                                {testResult.error}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="modal-footer">
                        <Dialog.Close asChild>
                          <button type="button" className="btn btn-secondary btn-sm" disabled={isTesting}>
                            Close
                          </button>
                        </Dialog.Close>
                        <button
                          type="submit"
                          className="btn btn-primary btn-sm flex items-center gap-1"
                          disabled={isTesting}
                        >
                          {isTesting ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
                          <span>{isTesting ? "Executing..." : "Run Test"}</span>
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
    </div>
  );
}
