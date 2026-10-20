
interface DataPoint {
  label: string;
  value: number;
  secondary?: number;
}

interface MiniChartProps {
  data: DataPoint[];
  height?: number;
  primaryColor?: string;
  secondaryColor?: string;
  emptyMessage?: string;
}

export function MiniChart({
  data,
  height = 160,
  primaryColor = "var(--accent)",
  secondaryColor = "var(--error)",
  emptyMessage = "No data available",
}: MiniChartProps) {
  if (!data.length) {
    return (
      <div className="minichart-empty" style={{ height }}>
        <span>{emptyMessage}</span>
      </div>
    );
  }

  const maxVal = Math.max(...data.map((d) => d.value + (d.secondary || 0)), 1);
  const barWidth = Math.max(4, Math.min(24, (600 - data.length * 2) / data.length));
  const svgWidth = data.length * (barWidth + 2);
  const chartH = height - 28;

  return (
    <div className="minichart-container">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${svgWidth} ${height}`}
        preserveAspectRatio="none"
      >
        {data.map((d, i) => {
          const totalH = ((d.value + (d.secondary || 0)) / maxVal) * chartH;
          const primaryH = (d.value / maxVal) * chartH;
          const secondaryH = totalH - primaryH;
          const x = i * (barWidth + 2);

          return (
            <g key={i}>
              <title>{`${d.label}\n${d.value}${d.secondary !== undefined ? ` / ${d.secondary} errors` : ""}`}</title>
              {secondaryH > 0 && (
                <rect
                  x={x}
                  y={chartH - totalH}
                  width={barWidth}
                  height={secondaryH}
                  fill={secondaryColor}
                  rx={1}
                  opacity={0.8}
                />
              )}
              <rect
                x={x}
                y={chartH - primaryH}
                width={barWidth}
                height={Math.max(0, primaryH)}
                fill={primaryColor}
                rx={1}
                opacity={0.7}
              />
            </g>
          );
        })}
      </svg>
      <div className="minichart-labels">
        <span>{data[0]?.label}</span>
        <span>{data[data.length - 1]?.label}</span>
      </div>
    </div>
  );
}
