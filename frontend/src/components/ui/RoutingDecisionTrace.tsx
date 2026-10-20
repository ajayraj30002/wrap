import { getProviderBadgeStyle } from "../../lib/providerBadges";

interface RoutingScoreFactor {
  name: string;
  score: number;
}

interface RoutingDecisionTraceProps {
  factors?: RoutingScoreFactor[];
  finalScore?: number;
  funnel?: {
    requested: string;
    totalCandidates: number;
    eligibleCount: number;
    filteredCount: number;
    competitiveCount: number;
    selectedModel: string;
  };
  policy?: string;
  decisionReason?: string;
  candidateWorkers?: string[];
}

export function RoutingDecisionTrace({
  factors,
  finalScore = 0.84,
  funnel = {
    requested: "auto",
    totalCandidates: 7,
    eligibleCount: 5,
    filteredCount: 2,
    competitiveCount: 3,
    selectedModel: "gemini-2.5-flash",
  },
  policy = "balanced",
  decisionReason,
  candidateWorkers,
}: RoutingDecisionTraceProps) {
  const defaultFactors: RoutingScoreFactor[] = [
    { name: "Capability", score: 0.92 },
    { name: "Latency", score: 0.81 },
    { name: "Reliability", score: 0.98 },
    { name: "Quota", score: 0.74 },
    { name: "Load", score: 0.63 },
  ];

  const activeFactors = factors || defaultFactors;
  const models = (funnel.selectedModel || "")
    .split(",")
    .map((m) => m.trim())
    .filter(Boolean);
  const isMulti = models.length > 1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
      {/* Funnel Step Flow */}
      <div className="funnel-trace-wrap">
        <div className="funnel-step">
          <span className="funnel-badge" style={{ borderColor: "var(--accent)" }}>{funnel.requested}</span>
          <span className="funnel-arrow">→</span>
        </div>
        <div className="funnel-step">
          <span className="funnel-badge">{funnel.totalCandidates} candidates</span>
          <span className="funnel-arrow">→</span>
        </div>
        <div className="funnel-step">
          <span className="funnel-badge">{funnel.eligibleCount} eligible</span>
          <span className="funnel-arrow">→</span>
        </div>
        <div className="funnel-step">
          <span className="funnel-badge" style={{ color: "var(--text-tertiary)" }}>
            {funnel.filteredCount} filtered
          </span>
          <span className="funnel-arrow">→</span>
        </div>
        <div className="funnel-step">
          <span className="funnel-badge">{funnel.competitiveCount} competitive</span>
          <span className="funnel-arrow">→</span>
        </div>
        <div className="funnel-step">
          <span
            className="funnel-badge"
            style={{
              borderColor: "var(--success)",
              color: "var(--success)",
              fontWeight: 600,
              maxWidth: "200px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={funnel.selectedModel}
          >
            {isMulti ? `DAG Mesh (${models.length} models)` : funnel.selectedModel}
          </span>
        </div>
      </div>

      {isMulti && (
        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", padding: "0.5rem 0.75rem", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)" }}>
          <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.05em", width: "100%", marginBottom: "0.2rem" }}>
            Dispatched Worker Models ({models.length})
          </span>
          {models.map((m) => {
            const b = getProviderBadgeStyle(undefined, m);
            return (
              <span
                key={m}
                style={{
                  fontSize: "0.6875rem",
                  fontFamily: "var(--font-mono)",
                  backgroundColor: b.bg,
                  border: `1px solid ${b.border}`,
                  color: b.color,
                  padding: "0.18rem 0.45rem",
                  borderRadius: "var(--radius-xs)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                }}
              >
                <span style={{ width: "5px", height: "5px", borderRadius: "50%", backgroundColor: b.dot }} />
                {m}
              </span>
            );
          })}
        </div>
      )}

      {/* Why this worker scoring breakdown */}
      <div className="score-breakdown-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "0.6875rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-tertiary)" }}>
            WHY THIS WORKER? (POLICY: {policy.toUpperCase()})
          </span>
          <span style={{ fontSize: "0.6875rem", color: "var(--text-secondary)" }}>0.0 – 1.0</span>
        </div>

        {activeFactors.map((f) => (
          <div key={f.name} className="score-row">
            <span className="score-name">{f.name}</span>
            <div className="score-bar-track">
              <div
                className="score-bar-fill"
                style={{ width: `${Math.round(f.score * 100)}%` }}
              />
            </div>
            <span className="score-val">{f.score.toFixed(2)}</span>
          </div>
        ))}

        <div className="final-score-callout">
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>
            FINAL ROUTE SCORE
          </span>
          <span className="final-score-val">{finalScore.toFixed(2)}</span>
        </div>
      </div>

      {decisionReason && (
        <div style={{ backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", padding: "0.75rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
          <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem", fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Scheduler Selection Rationale
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            {decisionReason}
          </div>
          {candidateWorkers && candidateWorkers.length > 0 && (
            <div style={{ marginTop: "0.5rem", fontSize: "0.6875rem", color: "var(--text-tertiary)", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.35rem" }}>
              Evaluated Candidates ({candidateWorkers.length}): <span style={{ fontFamily: "var(--font-mono)" }}>{candidateWorkers.map((w) => w.slice(0, 8)).join(", ")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
