interface ChartCardProps {
  title: string
  subtitle?: string
  children: React.ReactNode
}

export function ChartCard({ title, subtitle, children }: ChartCardProps) {
  return (
    <div style={{ background: '#1a1a2e', borderRadius: 6, overflow: 'hidden' }}>
      <div
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid #2a2a3e',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span style={{ fontWeight: 600, color: '#e2e8f0' }}>{title}</span>
        {subtitle && <span style={{ color: '#64748b', fontSize: 11 }}>{subtitle}</span>}
      </div>
      {children}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#334155', fontSize: 13 }}>
      {message}
    </div>
  )
}
