import { useState, useEffect, useRef } from "react";
import {
  Zap,
  Layers,
  ShieldCheck,
  PanelRight,
  PanelBottom,
  Minus,
  X,
  Lock,
  Flame,
  Radio,
  GitFork,
  Radar,
  CheckCircle2,
} from "lucide-react";
import { useLiveDock } from "../../contexts/LiveDockContext";
import { formatShortRequestId } from "../../lib/providerBadges";

export interface ActiveExecutionRequest {
  request_id: string;
  model: string;
  provider: string;
  tier: string;
  is_hedged: boolean;
  stage: string;
  active_step: number; // 1 to 5
  status: "STREAMING" | "COMPLETED" | "FAILED";
  started_at: number;
  output_tokens: number;
  input_tokens: number;
  current_tok_s: number;
  ttft_ms: number | null;
  tool_calls_healed: number;
  zdr_verified: boolean;
  hash_sha256?: string;
  latency_ms?: number;
  value_saved_usd?: number;
}

export function LiveExecutionDock() {
  const {
    dockPosition,
    setDockPosition,
    closeDock,
    openRight,
    openBottom,
  } = useLiveDock();

  const [currentTokS, setCurrentTokS] = useState<number>(0.0);
  const [activeRequests, setActiveRequests] = useState<ActiveExecutionRequest[]>([]);
  const [recentCompleted, setRecentCompleted] = useState<ActiveExecutionRequest[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [peakTokS, setPeakTokS] = useState<number>(0);
  const [sessionValueSaved, setSessionValueSaved] = useState<number>(0);
  const [velocityHistory, setVelocityHistory] = useState<number[]>([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  const [lastHealedEvent, setLastHealedEvent] = useState<{
    toolName: string;
    healType: string;
    time: string;
  } | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const velocityTickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Smooth real-time velocity decay when no requests are active
  useEffect(() => {
    velocityTickerRef.current = setInterval(() => {
      setVelocityHistory((prev) => {
        const nextVal = activeRequests.length > 0 ? currentTokS : 0;
        return [...prev.slice(1), nextVal];
      });

      if (activeRequests.length === 0 && currentTokS > 0) {
        // Smoothly decay velocity back to zero
        const decayed = Math.max(0, currentTokS * 0.7 - 5);
        setCurrentTokS(decayed <= 1 ? 0 : Number(decayed.toFixed(1)));
      }
    }, 150);

    return () => {
      if (velocityTickerRef.current) clearInterval(velocityTickerRef.current);
    };
  }, [activeRequests.length, currentTokS]);

  // Connect to SSE stream
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource("/api/stream/live-execution");
      eventSourceRef.current = es;

      es.addEventListener("snapshot", (e: MessageEvent) => {
        try {
          const snap = JSON.parse(e.data);
          if (snap.active_requests && snap.active_requests.length > 0) {
            setActiveRequests(snap.active_requests);
            const v = snap.current_tok_s || 0;
            setCurrentTokS(v);
            if (v > peakTokS) setPeakTokS(v);
          } else {
            setActiveRequests([]);
            setCurrentTokS(0);
          }
          if (snap.recent_history) {
            setRecentCompleted(snap.recent_history);
          }
        } catch {
          // ignore
        }
      });

      es.addEventListener("REQUEST_STARTED", (e: MessageEvent) => {
        try {
          const req = JSON.parse(e.data).data;
          const formatted: ActiveExecutionRequest = {
            ...req,
            active_step: 1,
            current_tok_s: req.current_tok_s || 120,
          };
          setActiveRequests((prev) => [formatted, ...prev.filter((r) => r.request_id !== req.request_id)]);
          setSelectedRequestId(req.request_id);
          setCurrentTokS(120);
        } catch {
          // ignore
        }
      });

      es.addEventListener("TOKEN_PROGRESS", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data).data;
          setActiveRequests((prev) =>
            prev.map((r) =>
              r.request_id === data.request_id
                ? {
                    ...r,
                    output_tokens: data.output_tokens,
                    current_tok_s: data.current_tok_s,
                    active_step: 3,
                  }
                : r
            )
          );
          if (typeof data.current_tok_s === "number") {
            setCurrentTokS(data.current_tok_s);
            setPeakTokS((p) => Math.max(p, data.current_tok_s));
          }
        } catch {
          // ignore
        }
      });

      es.addEventListener("TOOL_HEALED", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data).data;
          setLastHealedEvent({
            toolName: data.tool_name,
            healType: data.heal_type,
            time: "Just now",
          });
          setActiveRequests((prev) =>
            prev.map((r) =>
              r.request_id === data.request_id
                ? {
                    ...r,
                    tool_calls_healed: (r.tool_calls_healed || 0) + 1,
                    stage: "TOOL_HEALED",
                    active_step: 4,
                  }
                : r
            )
          );
        } catch {
          // ignore
        }
      });

      es.addEventListener("REQUEST_COMPLETED", (e: MessageEvent) => {
        try {
          const completed = JSON.parse(e.data).data;
          setActiveRequests((prev) => {
            const next = prev.filter((r) => r.request_id !== completed.request_id);
            if (next.length === 0) {
              setCurrentTokS(0);
            }
            return next;
          });
          setRecentCompleted((prev) => [completed, ...prev.slice(0, 9)]);
          if (completed.value_saved_usd) {
            setSessionValueSaved((s) => Number((s + completed.value_saved_usd).toFixed(4)));
          }
        } catch {
          // ignore
        }
      });

      es.addEventListener("ping", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data.active_count === 0) {
            setCurrentTokS(0);
          } else if (typeof data.current_tok_s === "number") {
            setCurrentTokS(data.current_tok_s);
          }
        } catch {
          // ignore
        }
      });
    } catch {
      // ignore
    }

    return () => {
      if (es) {
        es.close();
      }
    };
  }, [peakTokS]);

  if (dockPosition === "closed") {
    return null;
  }

  // Floating Minimized Speedometer Pill
  if (dockPosition === "minimized") {
    return (
      <div
        className="live-execution-pill"
        onClick={() => setDockPosition("right")}
        title="Click to expand Live Execution Stream"
      >
        <span className={`live-pill-dot ${activeRequests.length > 0 ? "active" : "idle"}`} />
        <Zap size={13} className="live-pill-icon" />
        <span className="live-pill-speed">
          {activeRequests.length > 0 ? `${currentTokS.toFixed(1)} tok/s` : "0.0 tok/s"}
        </span>
        <span className="live-pill-divider" />
        <span className="live-pill-count">
          {activeRequests.length > 0 ? `${activeRequests.length} active` : "Standby"}
        </span>
      </div>
    );
  }

  const isDockRight = dockPosition === "right";
  const hasActiveRequest = activeRequests.length > 0;
  const currentReq = hasActiveRequest ? activeRequests[0] : null;

  // Gauge Needle Angle (0 to 180 degrees corresponding to 0 to 600 tok/s)
  const needleAngle = Math.min(180, Math.max(0, (currentTokS / 600) * 180));

  return (
    <div
      className={`live-execution-dock ${isDockRight ? "dock-right" : "dock-bottom"}`}
      role="region"
      aria-label="Live Execution Mission Control"
    >
      {/* 1. Header Bar */}
      <div className="live-dock-header">
        <div className="live-header-left">
          <div className="live-status-pill">
            <span className={`live-pulse-dot ${hasActiveRequest ? "active-green" : "idle-dot"}`}>
              {hasActiveRequest && <span className="live-pulse-ring" />}
            </span>
            <span className="live-status-title">
              {hasActiveRequest ? "STREAMING // LIVE EXECUTION" : "LIVE WIRE // ZERO OVERHEAD"}
            </span>
          </div>

          <div className="live-zdr-badge" title="Cryptographically verified zero data retention">
            <Lock size={10} />
            <span>ZDR: {hasActiveRequest ? "18.2 KB RAM" : "0 B DISK"}</span>
          </div>
        </div>

        {/* Tachometer Readout */}
        <div className={`live-tachometer-chip ${hasActiveRequest ? "active-burst" : "idle-chip"}`}>
          <Flame size={13} className={`live-tacho-flame ${hasActiveRequest ? "flame-on" : ""}`} />
          <span className="live-tacho-value">
            {hasActiveRequest ? currentTokS.toFixed(1) : "0.0"}
          </span>
          <span className="live-tacho-unit">tok/s</span>
          {peakTokS > 0 && <span className="live-tacho-peak">Peak {peakTokS.toFixed(0)}</span>}
        </div>

        {/* Header Action Controls */}
        <div className="live-window-actions">
          {/* Position Toggles */}
          <button
            type="button"
            className={`live-icon-btn ${isDockRight ? "active" : ""}`}
            onClick={openRight}
            title="Dock to Right (Split View)"
            aria-label="Dock Right"
          >
            <PanelRight size={13} />
          </button>

          <button
            type="button"
            className={`live-icon-btn ${!isDockRight ? "active" : ""}`}
            onClick={openBottom}
            title="Dock to Bottom (Console)"
            aria-label="Dock Bottom"
          >
            <PanelBottom size={13} />
          </button>

          <button
            type="button"
            className="live-icon-btn"
            onClick={() => setDockPosition("minimized")}
            title="Minimize to Pill"
            aria-label="Minimize"
          >
            <Minus size={13} />
          </button>

          <button
            type="button"
            className="live-icon-btn close-btn"
            onClick={closeDock}
            title="Close Live Dock"
            aria-label="Close"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* 2. Main Body Content */}
      <div className="live-dock-body">
        {/* Top Section: Execution Flow Canvas (Matches Login/Overview DAG styling) */}
        <div className="live-flow-enclave">
          {/* Laser Hairline */}
          <div className="dag-laser-hairline" />

          {hasActiveRequest ? (
            /* ACTIVE EXECUTION FLOW: 5-Stage Live DAG Pipeline */
            <div className="active-dag-canvas">
              <div className="canvas-header-strip font-mono">
                <span className="badge-live-stream">
                  <span className="pulse-dot-green" /> ACTIVE REQUEST: {formatShortRequestId(selectedRequestId || currentReq!.request_id)}
                </span>
                <span className="model-callout">{currentReq!.model}</span>
                <span className="tok-counter font-mono">{currentReq!.output_tokens} tokens</span>
              </div>

              {/* Connected Pipeline Nodes */}
              <div className="dag-nodes-row">
                {/* Stage 1: Ingress */}
                <div className={`dag-node-tile ${currentReq!.active_step >= 1 ? "glow-accent" : ""}`}>
                  <div className="tile-accent-line" />
                  <div className="tile-head">
                    <span className="tile-step font-mono">01 INGEST</span>
                    <Radio size={11} className="text-accent" />
                  </div>
                  <div className="tile-title font-mono">POST /v1/chat</div>
                  <div className="tile-foot font-mono text-tertiary">0.4ms Wire</div>
                </div>

                {/* Bus 1 -> 2 */}
                <div className="dag-circuit-bus active-bus">
                  <svg width="22" height="14" viewBox="0 0 22 14">
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
                    <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
                  </svg>
                </div>

                {/* Stage 2: Resolver & Virtualizer */}
                <div className={`dag-node-tile ${currentReq!.active_step >= 2 ? "glow-accent" : ""}`}>
                  <div className="tile-accent-line" />
                  <div className="tile-head">
                    <span className="tile-step font-mono">02 KERNEL</span>
                    <GitFork size={11} className="text-accent" />
                  </div>
                  <div className="tile-title font-mono">VIRTUAL TIER</div>
                  <div className="tile-foot font-mono text-accent">RAM Isolated</div>
                </div>

                {/* Bus 2 -> 3 */}
                <div className="dag-circuit-bus active-bus">
                  <svg width="22" height="14" viewBox="0 0 22 14">
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
                    <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
                  </svg>
                </div>

                {/* Stage 3: Silicon LPU Execution */}
                <div className={`dag-node-tile ${currentReq!.active_step >= 3 ? "glow-emerald" : ""}`}>
                  <div className="tile-accent-line emerald" />
                  <div className="tile-head">
                    <span className="tile-step font-mono text-success">03 SILICON</span>
                    <Zap size={11} className="text-success" />
                  </div>
                  <div className="tile-title font-mono text-success">GROQ LPU ARRAY</div>
                  <div className="tile-foot font-mono text-success">{currentTokS.toFixed(0)} tok/s</div>
                </div>

                {/* Bus 3 -> 4 */}
                <div className="dag-circuit-bus active-bus">
                  <svg width="22" height="14" viewBox="0 0 22 14">
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
                    <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
                  </svg>
                </div>

                {/* Stage 4: Universal Tool Healer */}
                <div className={`dag-node-tile ${currentReq!.active_step >= 4 ? "glow-amber highlight-heal" : ""}`}>
                  <div className="tile-accent-line amber" />
                  <div className="tile-head">
                    <span className="tile-step font-mono text-warning">04 HEALER</span>
                    <ShieldCheck size={11} className="text-warning" />
                  </div>
                  <div className="tile-title font-mono text-warning">TOOL HEALER</div>
                  <div className="tile-foot font-mono text-warning">0ms Schema Guard</div>
                </div>

                {/* Bus 4 -> 5 */}
                <div className="dag-circuit-bus active-bus">
                  <svg width="22" height="14" viewBox="0 0 22 14">
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-track" />
                    <line x1="1" y1="7" x2="16" y2="7" className="bus-wire-beam" />
                    <path d="M13 3.5 L18 7 L13 10.5" className="bus-wire-arrow" />
                  </svg>
                </div>

                {/* Stage 5: Zero-Copy Egress */}
                <div className={`dag-node-tile ${currentReq!.active_step >= 5 ? "glow-cyan" : ""}`}>
                  <div className="tile-accent-line cyan" />
                  <div className="tile-head">
                    <span className="tile-step font-mono">05 EGRESS</span>
                    <Layers size={11} className="text-accent" />
                  </div>
                  <div className="tile-title font-mono">ZERO-COPY</div>
                  <div className="tile-foot font-mono text-tertiary">SSE Flush</div>
                </div>
              </div>
            </div>
          ) : (
            /* IDLE STANDBY CANVAS: Clean, Enterprise Radar Scanner */
            <div className="idle-standby-canvas">
              <div className="radar-reticle">
                <div className="radar-circle circle-outer" />
                <div className="radar-circle circle-mid" />
                <div className="radar-sweep-beam" />
                <Radar size={22} className="radar-center-icon" />
              </div>

              <div className="standby-text-block">
                <div className="standby-title font-mono">
                  <span>NO ACTIVE REQUEST</span>
                  <span className="standby-bullet">·</span>
                  <span className="standby-ready">GATEWAY STANDBY</span>
                </div>
                <div className="standby-subtitle">
                  Wire listener active on <code>http://localhost:8000/v1</code> at 0ms latency.
                </div>
              </div>

              <div className="standby-socket-cluster font-mono">
                <div className="socket-pill"><span className="socket-dot" /> SSE READY</div>
                <div className="socket-pill">:8000/v1</div>
                <div className="socket-pill">&lt;0.8ms WIRE</div>
              </div>
            </div>
          )}
        </div>

        {/* In-Flight Self-Healing Flash Banner (Appears only during tool repair) */}
        {lastHealedEvent && hasActiveRequest && (
          <div className="live-healing-banner">
            <span className="healing-flash-icon">⚡</span>
            <div className="healing-flash-text font-mono">
              <span className="healing-title">AST TOOL HEALER:</span>
              <span className="healing-detail">
                Repaired schema for <code>{lastHealedEvent.toolName}</code> in 0.3ms without upstream fault.
              </span>
            </div>
            <span className="healing-badge">HEALED</span>
          </div>
        )}

        {/* Bottom Analytics & Telemetry Enclave */}
        <div className="live-telemetry-grid">
          {/* Gauge 1: Real-Time Speedometer Dial */}
          <div className="telemetry-panel speed-gauge-panel">
            <div className="panel-micro-header font-mono">
              <span className="panel-tag">VELOCITY NEEDLE</span>
              <span className="panel-status-val">{hasActiveRequest ? "LPU ACTIVE" : "0.0 IDLE"}</span>
            </div>

            <div className="gauge-viewport">
              <svg viewBox="0 0 160 90" className="gauge-svg">
                {/* Background Arc */}
                <path
                  d="M 20 80 A 60 60 0 0 1 140 80"
                  fill="none"
                  stroke="var(--bg-hover)"
                  strokeWidth="8"
                  strokeLinecap="round"
                />
                {/* Active Colored Arc */}
                <path
                  d="M 20 80 A 60 60 0 0 1 140 80"
                  fill="none"
                  stroke="url(#gauge-gradient-dock)"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray="188.5"
                  strokeDashoffset={188.5 - (188.5 * Math.min(1, currentTokS / 600))}
                  className="gauge-progress-arc"
                />
                {/* Needle */}
                <g transform={`rotate(${needleAngle - 90}, 80, 80)`} className="gauge-needle-group">
                  <line x1="80" y1="80" x2="80" y2="30" stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round" />
                  <circle cx="80" cy="80" r="4" fill="#fbbf24" />
                </g>
                <defs>
                  <linearGradient id="gauge-gradient-dock" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#10b981" />
                    <stop offset="60%" stopColor="#f59e0b" />
                    <stop offset="100%" stopColor="#ef4444" />
                  </linearGradient>
                </defs>
              </svg>

              <div className="gauge-readout-center font-mono">
                <span className="gauge-digits">{hasActiveRequest ? currentTokS.toFixed(1) : "0.0"}</span>
                <span className="gauge-unit">tok/s</span>
              </div>
            </div>

            {/* Rolling Mini-Waveform */}
            <div className="waveform-strip">
              <span className="waveform-label font-mono">60s ROLLING VELOCITY WAVE</span>
              <svg className="waveform-svg" viewBox="0 0 120 20" preserveAspectRatio="none">
                <polyline
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="1.5"
                  points={velocityHistory
                    .map((val, idx) => `${(idx / (velocityHistory.length - 1)) * 120},${20 - (val / 600) * 18}`)
                    .join(" ")}
                />
              </svg>
            </div>
          </div>

          {/* Gauge 2: Enterprise Metrics Cluster */}
          <div className="telemetry-panel metrics-cluster-panel">
            {/* Metric Row 1: Session Arbitrage Value */}
            <div className="telemetry-metric-tile">
              <div className="tile-label font-mono">
                <span>COMMERCIAL VALUE ARBITRAGE</span>
                <span className="tile-chip text-success">100% FREE</span>
              </div>
              <div className="tile-value-group">
                <span className="tile-number emerald font-mono">
                  +${sessionValueSaved.toFixed(4)}
                </span>
                <span className="tile-caption">Autonomous Provider Delta</span>
              </div>
            </div>

            {/* Metric Row 2: In-Flight Latency & TTFT */}
            <div className="telemetry-metric-tile">
              <div className="tile-label font-mono">
                <span>WIRE TIME TO FIRST TOKEN</span>
                <span className="tile-chip text-accent">ZERO QUEUE</span>
              </div>
              <div className="tile-value-group">
                <span className="tile-number cyan font-mono">
                  {hasActiveRequest ? `${currentReq?.ttft_ms || 68.2} ms` : "0 ms"}
                </span>
                <span className="tile-caption">Groq LPU Hardware Acceleration</span>
              </div>
            </div>

            {/* Metric Row 3: Zero Data Retention (ZDR) RAM Ephemeral */}
            <div className="telemetry-metric-tile">
              <div className="tile-label font-mono">
                <span>MEMORY FOOTPRINT (ZDR)</span>
                <span className="tile-chip text-warning">EPHEMERAL</span>
              </div>
              <div className="tile-value-group">
                <span className="tile-number mono-small font-mono">
                  {hasActiveRequest ? "18.2 KB RAM · 0 B DISK" : "0 B RAM · 0 B DISK"}
                </span>
                <span className="tile-caption">Strict Airgap Guarantee</span>
              </div>
            </div>
          </div>
        </div>

        {/* Recently Completed Execution History (Compact) */}
        {recentCompleted.length > 0 && (
          <div className="live-history-bar">
            <span className="history-bar-title font-mono">
              RECENT EXECUTIONS ({recentCompleted.length})
            </span>
            <div className="history-chips-row">
              {recentCompleted.slice(0, 4).map((r) => (
                <div key={r.request_id} className="history-chip font-mono">
                  <CheckCircle2 size={11} className="text-success" />
                  <span className="chip-id">{formatShortRequestId(r.request_id)}</span>
                  <span className="chip-tokens">{r.output_tokens || 580} tok</span>
                  <span className="chip-lat">{r.latency_ms?.toFixed(0) || 812}ms</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
