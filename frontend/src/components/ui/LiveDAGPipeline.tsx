import { useState, useEffect, useCallback, type ElementType } from "react";
import {
  Code2,
  Cpu,
  ShieldCheck,
  Layers,
  Check,
  Play,
  Pause,
  RotateCcw,
  GitFork,
  Radio,
  X,
  CheckCircle2,
} from "lucide-react";

interface ParallelNode {
  id: string;
  icon: ElementType;
  name: string;
  engine: string;
  badge: string;
  tagColor: "cyan" | "amber" | "indigo" | "emerald";
  progressPct: number;
  description: string;
  capabilityRole: string;
  tierStrategy: string;
}

const PARALLEL_NODES: ParallelNode[] = [
  {
    id: "architecture",
    icon: Cpu,
    name: "System Architecture & Data",
    engine: "Frontier Reasoner (Gemini Pro)",
    badge: "DEEP REASONING",
    tagColor: "amber",
    progressPct: 95,
    description: "Database schema design, multi-tenant boundaries, and domain entity relationships formulated by high-capacity reasoners.",
    capabilityRole: "Deep Architectural Reasoning",
    tierStrategy: "Gemini Frontier Allocation",
  },
  {
    id: "api_logic",
    icon: Code2,
    name: "API & Service Logic",
    engine: "Groq LPU Ultra-Throughput",
    badge: "BURST ENGINE",
    tagColor: "cyan",
    progressPct: 80,
    description: "High-throughput procedural endpoints, authentication middleware, and RBAC security services generated at 500+ tok/s.",
    capabilityRole: "High-Speed Backend Synthesis",
    tierStrategy: "LPU Free-Tier Rotation",
  },
  {
    id: "client_ui",
    icon: Layers,
    name: "Client & Interface Layer",
    engine: "Fast Inference (Groq / Cerebras)",
    badge: "SPEED TIER",
    tagColor: "indigo",
    progressPct: 70,
    description: "Responsive React dashboards, interactive telemetry charts, and client-side state hooks generated in parallel.",
    capabilityRole: "Interactive Frontend Generation",
    tierStrategy: "Ultra-Fast Inference Clusters",
  },
  {
    id: "testing",
    icon: ShieldCheck,
    name: "Testing & Verification",
    engine: "Validation Suite Worker",
    badge: "FORMAL AUDIT",
    tagColor: "emerald",
    progressPct: 100,
    description: "Pytest unit and integration test fixtures, edge-case harnesses, and regression validation suites executed concurrently.",
    capabilityRole: "Automated Quality & Contract Testing",
    tierStrategy: "Parallel Test Worker Pool",
  },
  {
    id: "integration",
    icon: GitFork,
    name: "Cross-Contract Integration",
    engine: "Schema & Interface Aggregator",
    badge: "SYNTHESIS NODE",
    tagColor: "cyan",
    progressPct: 85,
    description: "Reconciles frontend-backend types, ensures OpenAPI schema adherence, and resolves dependency contracts before emission.",
    capabilityRole: "Cross-Workstream Contract Reconciliation",
    tierStrategy: "Autonomous Graph Synthesis",
  },
];

interface LiveDAGPipelineProps {
  onNodeSelect?: (nodeId: string | null) => void;
}

export function LiveDAGPipeline({ onNodeSelect }: LiveDAGPipelineProps) {
  const [activeStep, setActiveStep] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Dynamic looping wave across the 5 general pipeline stages
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setActiveStep((prev) => (prev >= 5 ? 1 : prev + 1));
    }, 1250);
    return () => clearInterval(timer);
  }, [isPlaying]);

  const handleTogglePlay = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  const handleReset = useCallback(() => {
    setActiveStep(1);
    setIsPlaying(true);
  }, []);

  const handleSelectNode = useCallback(
    (id: string) => {
      setSelectedNodeId((prev) => {
        const next = prev === id ? null : id;
        onNodeSelect?.(next);
        return next;
      });
    },
    [onNodeSelect]
  );

  const selectedParallelNode = PARALLEL_NODES.find((n) => n.id === selectedNodeId);

  return (
    <div
      className={`enterprise-dag-wrapper ${!isPlaying ? "is-paused" : ""}`}
      aria-label="Live Parallel DAG Execution Visualization"
    >
      {/* =========================================================================
          HUD CONTROL & GENERAL ARCHITECTURE HEADER
          ========================================================================= */}
      <header className="dag-hud-header">
        <div className="dag-hud-left">
          <div className="dag-live-beacon" title="Autonomous Multi-Agent AI Gateway Active">
            <span className="beacon-ping" />
            <span className="beacon-text font-mono">SELF-HEALING MULTI-AGENT DAG ENGINE</span>
          </div>

          <div className="dag-pipe-sep" />

          <span className="dag-mode-tag font-mono">PARALLEL SPECULATIVE ROUTING</span>
        </div>

        <div className="dag-hud-right">
          <div className="dag-hud-badges font-mono">
            <span className="dag-badge-chip">CONCURRENT DISPATCH</span>
            <span className="dag-badge-chip text-success">ZERO-COST ARBITRAGE</span>
          </div>

          <div className="dag-control-actions">
            <button
              type="button"
              className={`dag-action-btn ${!isPlaying ? "action-paused" : ""}`}
              onClick={handleTogglePlay}
              title={isPlaying ? "Pause pipeline simulation" : "Resume pipeline simulation"}
              aria-label={isPlaying ? "Pause pipeline simulation" : "Resume pipeline simulation"}
            >
              {isPlaying ? <Pause size={12} /> : <Play size={12} />}
            </button>

            <button
              type="button"
              className="dag-action-btn"
              onClick={handleReset}
              title="Reset flow wave to Step 1"
              aria-label="Reset flow wave to Step 1"
            >
              <RotateCcw size={12} />
            </button>
          </div>
        </div>
      </header>

      {/* =========================================================================
          MAIN DAG PIPELINE STAGES & CIRCUIT BUSES
          ========================================================================= */}
      <div className="dag-pipeline-canvas">
        {/* Laser beam border highlight at top */}
        <div className="dag-laser-hairline" />

        {/* -------------------------------------------------------------------
            STAGE 1: INGESTION (GENERAL CLIENT REQUEST)
            ------------------------------------------------------------------- */}
        <div
          className={`dag-node-card stage-ingress ${activeStep === 1 ? "active-glow" : ""} ${
            selectedNodeId === "ingress" ? "is-selected" : ""
          }`}
          onClick={() => handleSelectNode("ingress")}
          role="button"
          tabIndex={0}
          title="Ingress: OpenAI-compatible client chat completions endpoint"
        >
          <div className="dag-card-accent-bar" />
          <div className="dag-card-header">
            <span className="dag-step-index font-mono">01 INGEST</span>
            <Radio size={11} className="dag-step-icon text-accent" />
          </div>
          <div className="dag-card-body">
            <div className="dag-card-method font-mono">POST /v1/chat</div>
            <div className="dag-card-sub text-secondary">OpenAI Drop-In</div>
          </div>
          <div className="dag-card-footer font-mono">
            <span className="dag-pill-micro text-tertiary">Streaming SSE</span>
          </div>
        </div>

        {/* Conduit 1 -> 2: High-speed Ingest Bus */}
        <div className={`dag-bus-segment ${activeStep === 1 ? "active-bus" : ""}`} title="Ingress Bus">
          <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
            <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
            <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
            <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
          </svg>
        </div>

        {/* -------------------------------------------------------------------
            STAGE 2: ROUTER & ANALYZER (GENERAL DAG DECOMPOSITION)
            ------------------------------------------------------------------- */}
        <div
          className={`dag-node-card stage-router ${activeStep === 2 ? "active-glow" : ""} ${
            selectedNodeId === "router" ? "is-selected" : ""
          }`}
          onClick={() => handleSelectNode("router")}
          role="button"
          tabIndex={0}
          title="Resolver: Decomposes prompts into concurrent workstreams"
        >
          <div className="dag-card-accent-bar" />
          <div className="dag-card-header">
            <span className="dag-step-index font-mono">02 RESOLVER</span>
            <GitFork size={11} className="dag-step-icon text-accent" />
          </div>
          <div className="dag-card-body">
            <div className="dag-card-title font-mono" style={{ color: "var(--accent)" }}>
              DAG PARTITION
            </div>
            <div className="dag-card-sub text-secondary">Multi-Agent Split</div>
          </div>
          <div className="dag-card-footer font-mono">
            <span className="dag-pill-micro text-accent">Parallel Fan-Out</span>
          </div>
        </div>

        {/* Conduit 2 -> 3: Authentic SVG 1-to-5 Fan-Out Circuit Tree */}
        <div
          className={`dag-fan-out-container ${activeStep === 2 ? "active-fan" : ""}`}
          title="Concurrent Fan-Out Circuit Tree"
        >
          <svg
            width="32"
            height="196"
            viewBox="0 0 32 196"
            preserveAspectRatio="none"
            className="dag-fan-svg"
          >
            {/* 5 Branching Bezier Tracks */}
            <path d="M 0,98 C 16,98 16,18 32,18" className="fan-wire-track" />
            <path d="M 0,98 C 16,98 16,58 32,58" className="fan-wire-track" />
            <path d="M 0,98 L 32,98" className="fan-wire-track" />
            <path d="M 0,98 C 16,98 16,138 32,138" className="fan-wire-track" />
            <path d="M 0,98 C 16,98 16,178 32,178" className="fan-wire-track" />

            {/* Pulsing Light Photons along the 5 Beziers */}
            <path d="M 0,98 C 16,98 16,18 32,18" className="fan-wire-beam beam-0" />
            <path d="M 0,98 C 16,98 16,58 32,58" className="fan-wire-beam beam-1" />
            <path d="M 0,98 L 32,98" className="fan-wire-beam beam-2" />
            <path d="M 0,98 C 16,98 16,138 32,138" className="fan-wire-beam beam-3" />
            <path d="M 0,98 C 16,98 16,178 32,178" className="fan-wire-beam beam-4" />
          </svg>
        </div>

        {/* -------------------------------------------------------------------
            STAGE 3: 5 PARALLEL EXECUTION WORKSTREAMS (Clean, 2-Line, No Truncation)
            ------------------------------------------------------------------- */}
        <div className="dag-parallel-column" role="region" aria-label="Concurrent Workstreams">
          {PARALLEL_NODES.map((node) => {
            const Icon = node.icon;
            const isSelected = selectedNodeId === node.id;
            return (
              <div
                key={node.id}
                className={`dag-parallel-pill ${activeStep === 3 ? "active-glow" : ""} ${
                  isSelected ? "is-selected" : ""
                }`}
                onClick={() => handleSelectNode(node.id)}
                role="button"
                tabIndex={0}
                title={`${node.name} — ${node.engine}`}
              >
                {/* Latency background tint fill */}
                <div className="pill-backdrop-fill" style={{ width: `${node.progressPct}%` }} />

                {/* Animated shimmer timeline progress bar */}
                <div className="pill-shimmer-bar" style={{ width: `${node.progressPct}%` }}>
                  <div className="shimmer-sheen" />
                </div>

                {/* Left identity payload */}
                <div className="pill-content-left">
                  <span className={`pill-beacon-dot tag-${node.tagColor}`} />
                  <span className="pill-icon-box">
                    <Icon size={13} />
                  </span>
                  <div className="pill-titles">
                    <span className="pill-name">{node.name}</span>
                    <span className="pill-engine font-mono text-tertiary">{node.engine}</span>
                  </div>
                </div>

                {/* Right capability badge */}
                <div className="pill-content-right">
                  <span className={`pill-tag-badge font-mono badge-${node.tagColor}`}>{node.badge}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Conduit 3 -> 4: Authentic SVG 5-to-1 Fan-In Circuit Tree */}
        <div
          className={`dag-fan-in-container ${activeStep === 3 ? "active-fan" : ""}`}
          title="Convergence Aggregator Circuit Tree"
        >
          <svg
            width="32"
            height="196"
            viewBox="0 0 32 196"
            preserveAspectRatio="none"
            className="dag-fan-svg"
          >
            {/* 5 Converging Bezier Tracks */}
            <path d="M 0,18 C 16,18 16,98 32,98" className="fan-wire-track" />
            <path d="M 0,58 C 16,58 16,98 32,98" className="fan-wire-track" />
            <path d="M 0,98 L 32,98" className="fan-wire-track" />
            <path d="M 0,138 C 16,138 16,98 32,98" className="fan-wire-track" />
            <path d="M 0,178 C 16,178 16,98 32,98" className="fan-wire-track" />

            {/* Pulsing Light Photons converging into Synthesizer */}
            <path d="M 0,18 C 16,18 16,98 32,98" className="fan-wire-beam beam-in-0" />
            <path d="M 0,58 C 16,58 16,98 32,98" className="fan-wire-beam beam-in-1" />
            <path d="M 0,98 L 32,98" className="fan-wire-beam beam-in-2" />
            <path d="M 0,138 C 16,138 16,98 32,98" className="fan-wire-beam beam-in-3" />
            <path d="M 0,178 C 16,178 16,98 32,98" className="fan-wire-beam beam-in-4" />
          </svg>
        </div>

        {/* -------------------------------------------------------------------
            STAGE 4: INTEGRATE / SYNTHESIZE
            ------------------------------------------------------------------- */}
        <div
          className={`dag-node-card stage-integrate ${activeStep === 4 ? "active-glow" : ""} ${
            selectedNodeId === "integrate" ? "is-selected" : ""
          }`}
          onClick={() => handleSelectNode("integrate")}
          role="button"
          tabIndex={0}
          title="Aggregator: Speculative token interleaver synthesizes streams"
        >
          <div className="dag-card-accent-bar" />
          <div className="dag-card-header">
            <span className="dag-step-index font-mono">04 SYNTHESIZE</span>
            <Layers size={11} className="dag-step-icon text-accent" />
          </div>
          <div className="dag-card-body">
            <div className="dag-card-title font-mono">STREAM MERGE</div>
            <div className="dag-card-sub text-secondary">Token Interleave</div>
          </div>
          <div className="dag-card-footer font-mono">
            <span className="dag-pill-micro text-tertiary">Zero-Loss Stream</span>
          </div>
        </div>

        {/* Conduit 4 -> 5: Dispatch Verdict Bus */}
        <div className={`dag-bus-segment ${activeStep === 4 ? "active-bus" : ""}`} title="Output Bus">
          <svg width="22" height="14" viewBox="0 0 22 14" className="dag-bus-svg">
            <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
            <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
            <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
          </svg>
        </div>

        {/* -------------------------------------------------------------------
            STAGE 5: VERDICT / COMPLETE (200 OK)
            ------------------------------------------------------------------- */}
        <div
          className={`dag-node-card stage-complete ${activeStep === 5 ? "active-complete-glow" : ""} ${
            selectedNodeId === "complete" ? "is-selected" : ""
          }`}
          onClick={() => handleSelectNode("complete")}
          role="button"
          tabIndex={0}
          title="Verdict: Unified stream delivered with sub-second SLA"
        >
          <div className="dag-card-accent-bar bar-emerald" />
          <div className="dag-card-header">
            <span className="dag-step-index font-mono text-success">05 VERDICT</span>
            <CheckCircle2 size={11} className="dag-step-icon text-success" />
          </div>
          <div className="dag-card-body">
            <div className="dag-card-title text-success font-mono flex items-center gap-1">
              <Check size={12} className={activeStep === 5 ? "pop-check" : ""} />
              <span>200 OK</span>
            </div>
            <div className="dag-card-sub font-mono text-secondary">Unified Output</div>
          </div>
          <div className="dag-card-footer font-mono">
            <span className="dag-pill-micro text-success">Low-Latency SLA</span>
          </div>
        </div>
      </div>

      {/* =========================================================================
          INTERACTIVE ARCHITECTURE INSPECTOR / GLOBAL CAPABILITY RIBBON
          ========================================================================= */}
      {selectedParallelNode ? (
        <div className="dag-inspector-panel" role="region" aria-label="Architecture Inspector">
          <div className="inspector-header">
            <div className="inspector-title-group">
              <selectedParallelNode.icon size={13} className="text-accent" />
              <span className="inspector-name font-mono">{selectedParallelNode.name}</span>
              <span className="inspector-engine font-mono text-secondary">
                ({selectedParallelNode.engine})
              </span>
            </div>
            <div className="inspector-actions">
              <span className="inspector-badge font-mono">{selectedParallelNode.badge}</span>
              <button
                type="button"
                className="inspector-close-btn"
                onClick={() => setSelectedNodeId(null)}
                title="Close architecture inspector"
                aria-label="Close architecture inspector"
              >
                <X size={12} />
              </button>
            </div>
          </div>

          <div className="inspector-metrics-grid font-mono">
            <div className="inspector-metric-card">
              <span className="metric-title">EXECUTION TIER</span>
              <span className="metric-data text-accent">{selectedParallelNode.capabilityRole}</span>
              <span className="metric-desc">Autonomous Routing</span>
            </div>
            <div className="inspector-metric-card">
              <span className="metric-title">CONCURRENCY</span>
              <span className="metric-data text-primary">Parallel Non-Blocking</span>
              <span className="metric-desc">Concurrent Workstream</span>
            </div>
            <div className="inspector-metric-card">
              <span className="metric-title">ARBITRAGE STRATEGY</span>
              <span className="metric-data text-success">{selectedParallelNode.tierStrategy}</span>
              <span className="metric-desc">Automated Multiplexing</span>
            </div>
            <div className="inspector-metric-card">
              <span className="metric-title">STREAM ASSEMBLY</span>
              <span className="metric-data text-primary">Speculative Interleave</span>
              <span className="metric-desc">Zero Waterfall Delay</span>
            </div>
          </div>

          <p className="inspector-footnote font-sans">{selectedParallelNode.description}</p>
        </div>
      ) : (
        <footer className="dag-summary-ribbon font-sans">
          <div className="ribbon-item" title="Concurrent prompt decomposition across specialized LPUs">
            <span className="ribbon-pill font-mono pill-cyan">PARALLEL DAG</span>
            <span className="ribbon-copy">Multi-LPU Concurrent Dispatch</span>
          </div>
          <div className="ribbon-divider" />
          <div className="ribbon-item" title="Zero-overhead speculative stream synthesis with minimal critical path latency">
            <span className="ribbon-pill font-mono pill-indigo">LOW LATENCY</span>
            <span className="ribbon-copy">Zero-Waterfall Stream Assembly</span>
          </div>
          <div className="ribbon-divider" />
          <div className="ribbon-item" title="Automated free-tier key multiplexing with 100% uptime">
            <span className="ribbon-pill font-mono pill-amber">ARBITRAGE</span>
            <span className="ribbon-copy">100% Free-Tier Key Pooling</span>
          </div>
        </footer>
      )}
    </div>
  );
}
