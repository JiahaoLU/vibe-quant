interface ChartCardProps {
  title: string
  subtitle?: string
  children: React.ReactNode
}

export function ChartCard({ title, subtitle, children }: ChartCardProps) {
  return (
    <div className="glass chart-card">
      <div className="chart-card__header">
        <span className="chart-card__title">{title}</span>
        {subtitle && <span className="chart-card__subtitle">{subtitle}</span>}
      </div>
      <div className="chart-card__body">
        {children}
      </div>
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">{message}</div>
  )
}
