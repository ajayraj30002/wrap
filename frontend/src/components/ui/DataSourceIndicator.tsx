import { Info } from 'lucide-react';

export function DataSourceIndicator({ source }: { source: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-secondary" title="Source of this data">
      <Info size={12} />
      <span>{source}</span>
    </div>
  );
}
