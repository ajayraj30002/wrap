export interface TraceStep {
  name: string;
  durationMs: number;
  type?: "step" | "branch" | "synthesis";
  children?: TraceStep[];
}

interface ExecutionTraceProps {
  steps?: TraceStep[];
  totalMs?: number;
}

export function ExecutionTrace({ steps, totalMs }: ExecutionTraceProps) {
  const defaultSteps: TraceStep[] = [
    { name: "analyze", durationMs: 3, type: "step" },
    { name: "route", durationMs: 12, type: "step" },
    {
      name: "execute (DAG parallel)",
      durationMs: 721,
      type: "branch",
      children: [
        { name: "database", durationMs: 380 },
        { name: "api", durationMs: 412 },
        { name: "analytics", durationMs: 521 },
        { name: "frontend", durationMs: 436 },
        { name: "tests", durationMs: 721 },
        { name: "docs", durationMs: 418 },
      ],
    },
    { name: "synthesize", durationMs: 183, type: "synthesis" },
  ];

  const activeSteps = steps && steps.length > 0 ? steps : defaultSteps;
  const maxDuration = totalMs || 1000;

  return (
    <div className="execution-trace-tree">
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6875rem", color: "var(--text-tertiary)", paddingBottom: "0.25rem", borderBottom: "1px dashed var(--border-subtle)" }}>
        <span>EXECUTION GRAPH</span>
        <span>LATENCY</span>
      </div>

      {activeSteps.map((step, idx) => {
        const isLast = idx === activeSteps.length - 1;
        const branchChar = isLast ? "└──" : "├──";
        const widthPct = Math.min(100, Math.max(4, Math.round((step.durationMs / maxDuration) * 100)));

        return (
          <div key={step.name} style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            <div className="trace-item">
              <div className="trace-left">
                <span className="trace-tree-branch">{branchChar}</span>
                <span className="trace-name">{step.name}</span>
              </div>
              <div className="trace-right">
                <div className="trace-bar">
                  <div
                    className="trace-bar-inner"
                    style={{
                      width: `${widthPct}%`,
                      backgroundColor: step.type === "branch" ? "var(--accent)" : "var(--text-secondary)",
                    }}
                  />
                </div>
                <span className="trace-duration">{step.durationMs}ms</span>
              </div>
            </div>

            {/* Nested Parallel Children if any */}
            {step.children && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", paddingLeft: "1.25rem" }}>
                {step.children.map((child, cIdx) => {
                  const cLast = cIdx === step.children!.length - 1;
                  const cBranch = cLast ? "└──" : "├──";
                  const cPct = Math.min(100, Math.max(4, Math.round((child.durationMs / maxDuration) * 100)));

                  return (
                    <div key={child.name} className="trace-item" style={{ opacity: 0.9 }}>
                      <div className="trace-left">
                        <span className="trace-tree-branch" style={{ color: "var(--text-muted)" }}>{cBranch}</span>
                        <span style={{ color: "var(--text-secondary)", fontSize: "0.6875rem" }}>{child.name}</span>
                      </div>
                      <div className="trace-right">
                        <div className="trace-bar" style={{ height: "3px" }}>
                          <div
                            className="trace-bar-inner"
                            style={{ width: `${cPct}%`, backgroundColor: "var(--accent)" }}
                          />
                        </div>
                        <span className="trace-duration" style={{ fontSize: "0.625rem" }}>{child.durationMs}ms</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
