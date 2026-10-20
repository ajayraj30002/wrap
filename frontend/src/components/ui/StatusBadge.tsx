
export function StatusBadge({ status }: { status: string }) {
  let color = 'var(--text-tertiary)';
  let bg = 'transparent';
  let dot = 'var(--text-tertiary)';
  
  switch(status.toLowerCase()) {
    case 'success':
    case 'healthy':
    case 'active':
      color = 'var(--success)';
      bg = 'rgba(0,255,0,0.1)';
      dot = 'var(--success)';
      break;
    case 'error':
    case 'unhealthy':
    case 'revoked':
      color = 'var(--error)';
      bg = 'rgba(255,0,0,0.1)';
      dot = 'var(--error)';
      break;
    case 'disabled':
      color = 'var(--text-secondary)';
      bg = 'var(--bg-hover)';
      break;
  }
  
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '2px 8px', borderRadius: '12px', background: bg, color, fontSize: '12px', fontWeight: 600, textTransform: 'capitalize' }}>
      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: dot }} />
      {status}
    </div>
  );
}
