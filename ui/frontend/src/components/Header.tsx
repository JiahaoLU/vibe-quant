import type { Session, SseStatus } from '../types'

interface HeaderProps {
  sessions: Session[]
  selectedId: string | null
  liveSessionId: string | null
  onSelectSession: (id: string) => void
  equity: number | null
  pnl: number | null
  fillCount: number
  sseStatus: SseStatus
}

function sseColor(s: SseStatus): string {
  if (s === 'connected') return 'var(--green)'
  if (s === 'reconnecting') return 'var(--amber)'
  return 'var(--text-dim)'
}

export function Header({
  sessions,
  selectedId,
  liveSessionId,
  onSelectSession,
  equity,
  pnl,
  fillCount,
  sseStatus,
}: HeaderProps) {
  const isLive = selectedId !== null && selectedId === liveSessionId

  return (
    <header className="site-header">
      <span className="site-header__title">vibe-quant</span>
      <div className="site-header__divider" />
      {isLive && <div className="site-header__badge-live">● LIVE</div>}
      <select
        className="glass-btn"
        value={selectedId ?? ''}
        onChange={(e) => onSelectSession(e.target.value)}
      >
        {sessions.map((s) => (
          <option key={s.session_id} value={s.session_id} style={{ background: '#0d0e18' }}>
            {s.session_id.slice(0, 8)}…{' '}
            {s.ended_at === null ? '(live)' : new Date(s.started_at).toLocaleDateString()}
          </option>
        ))}
      </select>

      <div className="site-header__stats">
        {equity !== null && (
          <span>
            Equity{' '}
            <strong style={{ color: 'var(--green)' }}>${equity.toFixed(2)}</strong>
          </span>
        )}
        {pnl !== null && (
          <span>
            P&amp;L{' '}
            <strong style={{ color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
            </strong>
          </span>
        )}
        <span>
          Fills <strong style={{ color: 'var(--text-bright)' }}>{fillCount}</strong>
        </span>
        {isLive && (
          <span style={{ color: sseColor(sseStatus) }}>
            <span className="sse-dot" style={{ background: sseColor(sseStatus) }} />
            {sseStatus}
          </span>
        )}
      </div>
    </header>
  )
}
