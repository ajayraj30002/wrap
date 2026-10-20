import { useState, useEffect, useCallback } from "react";
import { 
  CheckCircle2, 
  Split, 
  Sparkles, 
  Database, 
  Code, 
  Activity, 
  Layout, 
  FileText, 
  Check, 
  AlertCircle, 
  Zap, 
  Shield, 
  Cpu, 
  Layers, 
  Play, 
  Pause, 
  RotateCcw, 
  Radio, 
  GitFork, 
} from "lucide-react";
import { CopyButton } from "./CopyButton";
import { apiClient } from "../../lib/apiClient";

export interface DAGNode {
  id: string;
  name: string;
  category: "api" | "db" | "analytics" | "frontend" | "tests" | "docs";
  node_type?: string;
  model: string;
  provider?: string;
  latency_ms: number;
  status: "completed" | "failed" | "running" | "skipped";
  depends_on?: string[];
  input_tokens?: number;
  output_tokens?: number;
  retry_count?: number;
}

export interface DAGRunData {
  request_id: string;
  execution_mode: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  total_execution_ms: number;
  critical_path_ms: number;
  parallel_speedup: number;
  node_count: number;
  completed_nodes: number;
  failed_nodes: number;
  nodes: DAGNode[];
}



interface DAGTopologyProps {
  onNodeSelect?: (node: DAGNode) => void;
  selectedRequestId?: string;
  initialDagData?: DAGRunData | null;
  realWorkers?: Array<{ id: string; name?: string; model: string; provider: string; p50Ms?: number }>;
}

export function DAGTopology({
  onNodeSelect,
  selectedRequestId,
  initialDagData,
  realWorkers: _realWorkers,
}: DAGTopologyProps) {
  const [dagData, setDagData] = useState<DAGRunData | null>(initialDagData || null);
  const [selectedNode, setSelectedNode] = useState<DAGNode | null>(() => {
    if (initialDagData?.nodes && initialDagData.nodes.length > 0) {
      return initialDagData.nodes[0];
    }
    return null;
  });
  const [loading, setLoading] = useState<boolean>(!initialDagData);
  const [activeWaveStep, setActiveWaveStep] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);

  useEffect(() => {
    if (initialDagData) {
      setDagData(initialDagData);
      setLoading(false);
      if (initialDagData.nodes && initialDagData.nodes.length > 0) {
        setSelectedNode((prev) => {
          if (prev) {
            const matched = initialDagData.nodes.find((n: DAGNode) => n.id === prev.id);
            if (matched) return matched;
          }
          return initialDagData.nodes[0];
        });
      }
    }
  }, [initialDagData]);

  const fetchDAG = useCallback(async (targetId: string) => {
    try {
      setLoading(true);
      const res = await apiClient.get(`/api/execution/runs/${encodeURIComponent(targetId)}`);
      if (res && res.nodes && Array.isArray(res.nodes)) {
        setDagData(res);
        if (res.nodes.length > 0) {
          setSelectedNode((prev) => {
            if (prev) {
              const matched = res.nodes.find((n: DAGNode) => n.id === prev.id);
              if (matched) return matched;
            }
            return res.nodes[0];
          });
        }
      }
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialDagData !== undefined) {
      if (selectedRequestId && selectedRequestId !== dagData?.request_id) {
        fetchDAG(selectedRequestId);
      }
      return;
    }

    if (selectedRequestId && selectedRequestId !== dagData?.request_id) {
      fetchDAG(selectedRequestId);
    } else if (!dagData) {
      fetchDAG("latest");
    }
  }, [selectedRequestId, initialDagData, dagData?.request_id, fetchDAG]);

  // Dynamic looping wave simulation across the stages (identical to Login LiveDAGPipeline)
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setActiveWaveStep((prev) => (prev >= 5 ? 1 : prev + 1));
    }, 1250);
    return () => clearInterval(timer);
  }, [isPlaying]);

  const handleTogglePlay = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  const handleReset = useCallback(() => {
    setActiveWaveStep(1);
    setIsPlaying(true);
  }, []);

  const getCategoryIcon = (cat: string) => {
    switch (cat) {
      case "api": return <Code size={13} style={{ color: "var(--accent)" }} />;
      case "db": return <Database size={13} style={{ color: "var(--warning)" }} />;
      case "analytics": return <Activity size={13} style={{ color: "#a855f7" }} />;
      case "frontend": return <Layout size={13} style={{ color: "var(--success)" }} />;
      case "tests": return <CheckCircle2 size={13} style={{ color: "#06b6d4" }} />;
      case "docs": return <FileText size={13} style={{ color: "#f97316" }} />;
      default: return <Sparkles size={13} />;
    }
  };

  const getNodeIcon = (node: DAGNode) => {
    const name = (node.name || "").toLowerCase();
    const cat = (node.category || "").toLowerCase();
    if (name.includes("shield") || name.includes("guard") || cat.includes("shield")) {
      return <Shield size={13} style={{ color: "#38bdf8" }} />;
    }
    if (name.includes("cache") || name.includes("fastpath") || cat.includes("cache")) {
      return <Zap size={13} style={{ color: "#38bdf8" }} />;
    }
    if (name.includes("logic") || name.includes("verif") || name.includes("eval")) {
      return <Cpu size={13} style={{ color: "#818cf8" }} />;
    }
    if (name.includes("ground") || name.includes("data") || cat === "db") {
      return <Layers size={13} style={{ color: "#38bdf8" }} />;
    }
    if (name.includes("code") || name.includes("synthes") || cat === "api") {
      return <Code size={13} style={{ color: "#38bdf8" }} />;
    }
    return getCategoryIcon(node.category);
  };

  const handleNodeClick = (node: DAGNode) => {
    setSelectedNode(node);
    if (onNodeSelect) onNodeSelect(node);
  };

  // Render unified skeleton shimmer view while initial topology is loading
  if (!dagData) {
    return (
      <div className="topology-container">
        <div className="topology-header">
          <div className="topology-title">
            <Split size={14} style={{ color: "var(--accent)" }} />
            <span>Live Execution Flow</span>
            <span className="dag-live-indicator">
              <span className="dag-live-dot" /> LIVE DAG
            </span>
            <span className="skeleton-shimmer skeleton-line" style={{ width: "140px", height: "12px" }} />
          </div>
          <div className="topology-legend" style={{ display: "flex", gap: "0.75rem" }}>
            <span className="skeleton-shimmer skeleton-pill" style={{ width: "95px", height: "16px" }} />
            <span className="skeleton-shimmer skeleton-pill" style={{ width: "135px", height: "16px" }} />
          </div>
        </div>

        <div className="topology-viewport">
          <div className="dag-pipeline-track" style={{ opacity: 0.7 }}>
            <div className="dag-card-node" style={{ width: "120px" }}>
              <span className="skeleton-shimmer skeleton-line" style={{ width: "50px", height: "10px", marginBottom: "4px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "90px", height: "14px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "70px", height: "10px", marginTop: "4px" }} />
            </div>

            <div className="dag-bus-segment" style={{ opacity: 0.4 }}>
              <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
                <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
              </svg>
            </div>

            <div className="dag-card-node" style={{ width: "120px" }}>
              <span className="skeleton-shimmer skeleton-line" style={{ width: "45px", height: "10px", marginBottom: "4px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "70px", height: "14px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "75px", height: "10px", marginTop: "4px" }} />
            </div>

            <div className="dag-bus-segment" style={{ opacity: 0.4 }}>
              <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
                <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
              </svg>
            </div>

            <div className="dag-fan-col" style={{ minWidth: "220px", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              <div className="skeleton-shimmer skeleton-card" style={{ height: "38px" }} />
              <div className="skeleton-shimmer skeleton-card" style={{ height: "38px" }} />
            </div>

            <div className="dag-bus-segment" style={{ opacity: 0.4 }}>
              <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
                <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
              </svg>
            </div>

            <div className="dag-card-node" style={{ width: "120px" }}>
              <span className="skeleton-shimmer skeleton-line" style={{ width: "50px", height: "10px", marginBottom: "4px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "80px", height: "14px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "65px", height: "10px", marginTop: "4px" }} />
            </div>

            <div className="dag-bus-segment" style={{ opacity: 0.4 }}>
              <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
                <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
              </svg>
            </div>

            <div className="dag-card-node" style={{ width: "120px" }}>
              <span className="skeleton-shimmer skeleton-line" style={{ width: "55px", height: "10px", marginBottom: "4px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "50px", height: "14px" }} />
              <span className="skeleton-shimmer skeleton-line" style={{ width: "85px", height: "10px", marginTop: "4px" }} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Derive stages from authentic database records
  const allNodes: DAGNode[] = dagData.nodes || [];
  
  // Parallel branch subtasks (root tasks or tasks of type subtask)
  const parallelBranches: DAGNode[] = allNodes.filter(
    (n) => (!n.depends_on || n.depends_on.length === 0) || n.node_type === "subtask"
  );

  const branchNodes = parallelBranches.length > 0 ? parallelBranches : allNodes;
  const maxBranchLatency = Math.max(...branchNodes.map((n) => n.latency_ms || 0), 10);

  // Aggregation / integration step
  const integrationNode: DAGNode | undefined = allNodes.find(
    (n) => n.node_type === "aggregation" || ((n.depends_on?.length || 0) > 1 && n.node_type !== "synthesis")
  );

  // Final synthesis step
  const synthesisNode: DAGNode | undefined = allNodes.find(
    (n) => n.node_type === "synthesis" || n.id.includes("synthesis")
  );

  const displayReqId = dagData.request_id || selectedRequestId || "";
  const speedupVal = dagData.parallel_speedup ? `${dagData.parallel_speedup.toFixed(2)}x` : "1.00x";
  const completedCount = dagData.completed_nodes;
  const totalCount = dagData.node_count;
  const wallClockMs = dagData.total_execution_ms || 0;
  const criticalPathMs = dagData.critical_path_ms || wallClockMs;
  const overheadMs = Math.max(0, wallClockMs - criticalPathMs);
  const branchCount = Math.max(1, branchNodes.length);
  const fanHeight = Math.max(180, branchCount * 42);
  const centerY = Math.round(fanHeight / 2);
  const padding = 20;
  const branchYs = branchNodes.map((_, i) =>
    branchCount === 1 ? centerY : Math.round(padding + (i / (branchCount - 1)) * (fanHeight - padding * 2))
  );

  return (
    <div className="topology-container">
      <div className="topology-header">
        <div className="topology-title">
          <Split size={15} style={{ color: "var(--accent)" }} />
          <span>Live Execution Flow</span>
          <span className="dag-live-indicator">
            <span className="dag-live-dot" /> LIVE DAG
          </span>
          {displayReqId && (
            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-xs)", padding: "0.1rem 0.4rem" }}>
              <span style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>Active Request:</span>
              <span className="font-mono text-primary" style={{ fontSize: "0.6875rem", fontWeight: 600 }}>{displayReqId.length > 20 ? `${displayReqId.slice(0, 18)}...` : displayReqId}</span>
              <CopyButton text={displayReqId} className="btn-xs" />
            </div>
          )}
        </div>
        <div className="topology-legend">
          <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <button
              type="button"
              className={`topology-replay-btn ${!isPlaying ? "action-paused" : ""}`}
              onClick={handleTogglePlay}
              title={isPlaying ? "Pause pipeline simulation" : "Resume pipeline simulation"}
            >
              {isPlaying ? <Pause size={10} /> : <Play size={10} />}
              <span>{isPlaying ? "Simulating..." : "Paused"}</span>
            </button>
            <button
              type="button"
              className="topology-replay-btn"
              onClick={handleReset}
              title="Reset flow wave to Step 1"
            >
              <RotateCcw size={10} />
            </button>
          </div>
          <span className="topology-legend-badge">
            <span
              className={`status-dot ${loading ? "running" : (dagData?.status === "failed" ? "degraded" : "healthy")}`}
            />
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
              <strong className="font-mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                {completedCount} / {totalCount}
              </strong>
              <span style={{ color: "var(--text-tertiary)" }}>Succeeded</span>
            </span>
          </span>
          <span className="topology-legend-badge speedup">
            <Zap size={12} style={{ color: "var(--accent)", flexShrink: 0 }} />
            <span>
              Parallel Speedup: <strong className="font-mono">{speedupVal}</strong>
            </span>
          </span>
        </div>
      </div>

      <div className="topology-viewport" style={{ position: "relative" }}>
        {/* Laser beam border highlight at top like Login page */}
        <div className="dag-laser-hairline" />

        <div className="topology-flow" style={{ position: "relative", alignItems: "center" }}>
          {/* Step 1: Ingest */}
          <div
            className={`dag-node-card stage-ingress ${activeWaveStep === 1 ? "active-glow" : ""} ${
              selectedNode?.id === "ingress" ? "is-selected" : ""
            }`}
            onClick={() => setSelectedNode(null)}
            role="button"
            tabIndex={0}
            title={`Active Request: ${displayReqId}`}
          >
            <div className="dag-card-accent-bar" />
            <div className="dag-card-header">
              <span className="dag-step-index font-mono">01 INGEST</span>
              <Radio size={11} className="dag-step-icon text-accent" />
            </div>
            <div className="dag-card-body">
              <div className="dag-card-method font-mono">POST /v1/chat</div>
              <div className="dag-card-sub text-secondary font-mono" style={{ fontSize: "0.625rem" }} title={displayReqId}>
                {displayReqId.length > 14 ? `${displayReqId.slice(0, 12)}…` : displayReqId}
              </div>
            </div>
            <div className="dag-card-footer font-mono">
              <span className="dag-pill-micro text-tertiary">Streaming SSE</span>
            </div>
          </div>

          {/* Conduit 1 -> 2: High-speed Ingest Bus */}
          <div className={`dag-bus-segment ${activeWaveStep === 1 ? "active-bus" : ""}`} title="Ingress Bus">
            <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
              <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
              <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
              <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
            </svg>
          </div>

          {/* Step 2: Resolver */}
          <div
            className={`dag-node-card stage-router ${activeWaveStep === 2 ? "active-glow" : ""} ${
              selectedNode?.id === "router" ? "is-selected" : ""
            }`}
            onClick={() => setSelectedNode(null)}
            role="button"
            tabIndex={0}
            title={`Decomposes prompt into ${branchNodes.length} workstreams`}
          >
            <div className="dag-card-accent-bar" />
            <div className="dag-card-header">
              <span className="dag-step-index font-mono">02 RESOLVER</span>
              <GitFork size={11} className="dag-step-icon text-accent" />
            </div>
            <div className="dag-card-body">
              <div className="dag-card-title font-mono" style={{ color: "var(--accent)", fontSize: "0.75rem", fontWeight: 700 }}>
                {dagData?.execution_mode || "DAG"} MODE
              </div>
              <div className="dag-card-sub text-secondary font-mono" style={{ fontSize: "0.625rem" }}>
                Multi-Agent Split
              </div>
            </div>
            <div className="dag-card-footer font-mono">
              <span className="dag-pill-micro text-accent">{branchNodes.length} workstreams</span>
            </div>
          </div>

          {/* Conduit 2 -> 3: Authentic SVG 1-to-N Fan-Out Circuit Tree */}
          <div
            className={`dag-fan-out-container ${activeWaveStep === 2 ? "active-fan" : ""}`}
            style={{ height: `${fanHeight}px` }}
            title="Concurrent Fan-Out Circuit Tree"
          >
            <svg
              width="32"
              height={fanHeight}
              viewBox={`0 0 32 ${fanHeight}`}
              preserveAspectRatio="none"
              className="dag-fan-svg"
              style={{ height: `${fanHeight}px` }}
            >
              {branchYs.map((y, idx) => (
                <path
                  key={`fan-track-${idx}`}
                  d={`M 0,${centerY} C 16,${centerY} 16,${y} 32,${y}`}
                  className="fan-wire-track"
                />
              ))}
              {branchYs.map((y, idx) => (
                <path
                  key={`fan-beam-${idx}`}
                  d={`M 0,${centerY} C 16,${centerY} 16,${y} 32,${y}`}
                  className={`fan-wire-beam beam-${idx % 5}`}
                />
              ))}
            </svg>
          </div>

          {/* Step 3: DAG Parallel Branches with Shimmer Bars & Glow */}
          <div className="dag-parallel-column" style={{ minWidth: "320px", maxWidth: "380px" }}>
            {branchNodes.map((node) => {
              const isSelected = selectedNode?.id === node.id;
              const isFailed = node.status === "failed";
              const latPct = Math.min(100, Math.max(8, Math.round(((node.latency_ms || 0) / maxBranchLatency) * 100)));
              const mLower = (node.model || "").toLowerCase();
              const beaconClass = isFailed
                ? "tag-amber"
                : mLower.includes("gemini")
                ? "tag-indigo"
                : mLower.includes("groq") || mLower.includes("llama") || mLower.includes("oss")
                ? "tag-cyan"
                : "tag-emerald";

              return (
                <div
                  key={node.id}
                  className={`dag-parallel-pill ${isSelected ? "is-selected" : ""} ${activeWaveStep === 3 ? "active-glow" : ""}`}
                  onClick={() => handleNodeClick(node)}
                  role="button"
                  tabIndex={0}
                  title={`Worker Model: ${node.model} | Latency: ${node.latency_ms}ms`}
                >
                  <div className="pill-backdrop-fill" style={{ width: `${latPct}%` }} />
                  <div className="pill-shimmer-bar" style={{ width: `${latPct}%` }}>
                    <div className="shimmer-sheen" />
                  </div>

                  <div className="pill-content-left">
                    <span className={`pill-beacon-dot ${beaconClass}`} />
                    <span className="pill-icon-box">
                      {getNodeIcon(node)}
                    </span>
                    <div className="pill-titles">
                      <span className="pill-name">{node.name}</span>
                      <span className="pill-engine font-mono text-tertiary">{node.model}</span>
                    </div>
                  </div>

                  <div className="pill-content-right">
                    <span className="pill-tag-badge font-mono badge-cyan" style={{ fontSize: "0.625rem" }}>
                      {node.latency_ms > 0 ? `${node.latency_ms}ms` : (isFailed ? "failed" : "0ms")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Conduit 3 -> 4: Authentic SVG N-to-1 Fan-In Circuit Tree */}
          <div
            className={`dag-fan-in-container ${activeWaveStep === 3 ? "active-fan" : ""}`}
            style={{ height: `${fanHeight}px` }}
            title="Convergence Aggregator Circuit Tree"
          >
            <svg
              width="32"
              height={fanHeight}
              viewBox={`0 0 32 ${fanHeight}`}
              preserveAspectRatio="none"
              className="dag-fan-svg"
              style={{ height: `${fanHeight}px` }}
            >
              {branchYs.map((y, idx) => (
                <path
                  key={`fan-in-track-${idx}`}
                  d={`M 0,${y} C 16,${y} 16,${centerY} 32,${centerY}`}
                  className="fan-wire-track"
                />
              ))}
              {branchYs.map((y, idx) => (
                <path
                  key={`fan-in-beam-${idx}`}
                  d={`M 0,${y} C 16,${y} 16,${centerY} 32,${centerY}`}
                  className={`fan-wire-beam beam-in-${idx % 5}`}
                />
              ))}
            </svg>
          </div>

          {/* Step 4: Synthesize */}
          <div
            className={`dag-node-card stage-integrate ${activeWaveStep === 4 ? "active-glow" : ""} ${
              selectedNode?.id === (integrationNode?.id || synthesisNode?.id) ? "is-selected" : ""
            }`}
            onClick={() => integrationNode && handleNodeClick(integrationNode)}
            role="button"
            tabIndex={0}
            title={integrationNode ? `${integrationNode.name} (${integrationNode.model})` : "Synthesizes parallel streams"}
          >
            <div className="dag-card-accent-bar" />
            <div className="dag-card-header">
              <span className="dag-step-index font-mono">04 SYNTHESIZE</span>
              <Layers size={11} className="dag-step-icon text-accent" />
            </div>
            <div className="dag-card-body">
              <div className="dag-card-title font-mono" style={{ fontSize: "0.75rem", fontWeight: 700 }}>
                STREAM MERGE
              </div>
              <div
                className="dag-card-sub text-secondary font-mono"
                style={{ fontSize: "0.625rem" }}
                title={integrationNode ? integrationNode.name : "Token Interleave"}
              >
                {integrationNode
                  ? (integrationNode.name === "Integration & Merge" ? "Token Interleave" : integrationNode.name)
                  : "Token Interleave"}
              </div>
            </div>
            <div className="dag-card-footer font-mono">
              <span className="dag-pill-micro text-tertiary">
                {integrationNode ? `${integrationNode.latency_ms}ms` : `${overheadMs}ms overhead`}
              </span>
            </div>
          </div>

          {/* Conduit 4 -> 5: Dispatch Verdict Bus */}
          <div className={`dag-bus-segment ${activeWaveStep === 4 ? "active-bus" : ""}`} title="Output Bus">
            <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
              <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
              <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
              <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
            </svg>
          </div>

          {/* Step 5: Verdict */}
          <div
            className={`dag-node-card stage-complete ${activeWaveStep === 5 ? "active-complete-glow" : ""}`}
            style={{
              borderColor: dagData?.status === "failed" ? "var(--error-border)" : "rgba(16, 185, 129, 0.4)",
            }}
          >
            <div className="dag-card-accent-bar bar-emerald" />
            <div className="dag-card-header">
              <span className="dag-step-index font-mono text-success">05 VERDICT</span>
              <CheckCircle2 size={11} className="dag-step-icon text-success" />
            </div>
            <div className="dag-card-body">
              <div className="dag-card-title text-success font-mono flex items-center gap-1" style={{ fontSize: "0.75rem", fontWeight: 700 }}>
                {dagData?.status === "failed" ? (
                  <>
                    <AlertCircle size={12} />
                    <span>Error</span>
                  </>
                ) : (
                  <>
                    <Check size={12} className={activeWaveStep === 5 ? "pop-check" : ""} />
                    <span>200 OK</span>
                  </>
                )}
              </div>
              <div className="dag-card-sub font-mono text-secondary" style={{ fontSize: "0.625rem" }}>
                Unified Output
              </div>
            </div>
            <div className="dag-card-footer font-mono">
              <span className="dag-pill-micro text-success">
                {wallClockMs < 1000 ? `${wallClockMs}ms` : `${(wallClockMs / 1000).toFixed(2)}s`}
              </span>
            </div>
          </div>
        </div>

        {/* Selected Node Real Telemetry Inspector */}
        {selectedNode && (
          <div className="topology-inspector">
            <div className="topology-inspector-node">
              <span className="topology-inspector-icon">
                {getCategoryIcon(selectedNode.category)}
              </span>
              <span className="topology-inspector-name">{selectedNode.name}</span>
              <span className="topology-inspector-id font-mono">
                {selectedNode.id}
              </span>
            </div>
            <div className="topology-inspector-metrics">
              <div className="topology-metric-chip">
                <span className="topology-metric-label">Model</span>
                <strong className="topology-metric-value font-mono" style={{ color: "var(--accent)" }}>
                  {selectedNode.model}
                </strong>
              </div>
              <div className="topology-metric-chip">
                <span className="topology-metric-label">Latency</span>
                <strong className="topology-metric-value font-mono" style={{ color: "var(--text-primary)" }}>
                  {selectedNode.latency_ms}ms
                </strong>
              </div>
              <div className="topology-metric-chip">
                <span className="topology-metric-label">Tokens</span>
                <strong className="topology-metric-value font-mono" style={{ color: "var(--text-primary)" }}>
                  {selectedNode.input_tokens || 0} in / {selectedNode.output_tokens || 0} out
                </strong>
              </div>
              <div className="topology-metric-chip">
                <span className="topology-metric-label">Status</span>
                <span
                  className="topology-metric-value font-mono"
                  style={{
                    color: selectedNode.status === "completed" ? "var(--success)" : "var(--error)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.3rem",
                  }}
                >
                  <span
                    className={`status-dot ${selectedNode.status === "completed" ? "healthy" : "failed"}`}
                  />
                  <span style={{ fontWeight: 600 }}>{selectedNode.status}</span>
                </span>
              </div>
              {selectedNode.depends_on && selectedNode.depends_on.length > 0 && (
                <div className="topology-metric-chip">
                  <span className="topology-metric-label">Depends</span>
                  <strong className="topology-metric-value font-mono" style={{ color: "var(--text-secondary)" }}>
                    {selectedNode.depends_on.join(", ")}
                  </strong>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
