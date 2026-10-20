
export function LoadingSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row">
          {Array.from({ length: cols }).map((_, j) => (
            <div key={j} className="skeleton-cell" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function MetricSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="metric-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="metric-card">
          <div className="skeleton-line skeleton-sm" />
          <div className="skeleton-line skeleton-lg" style={{ marginTop: "0.5rem" }} />
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card">
      <div className="card-header">
        <div className="skeleton-line skeleton-md" />
      </div>
      <div className="card-body">
        <div className="skeleton-line skeleton-full" />
        <div className="skeleton-line skeleton-full" style={{ marginTop: "0.5rem" }} />
        <div className="skeleton-line skeleton-md" style={{ marginTop: "0.5rem" }} />
      </div>
    </div>
  );
}
