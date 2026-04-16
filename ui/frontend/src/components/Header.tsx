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

const S: Record<string, React.CSSProperties> = {
  bar: {
    background: '#0f0f1a',
    padding: '10px 16px',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    borderBottom: '1px solid #2a2a3e',
    fontFamily: 'system-ui, sans-serif',
  },
  title: { color: '#e2e8f0', fontWeight: 700, fontSize: 15 },
  divider: { width: 1, height: 16, background: '#2a2a3e' },
  liveBadge: {
    background: '#e74c3c',
    color: 'white',
    padding: '2px 9px',
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
  },
  select: {
    background: '#1a1a2e',
    color: '#94a3b8',
    border: '1px solid #2a2a3e',
    borderRadius: 5,
    padding: '3px 8px',
    fontSize: 12,
  },
  stats: { marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 12, color: '#64748b' },
}

function sseColor(s: SseStatus) {
  if (s === 'connected') return '#3b82f6'
  if (s === 'reconnecting') return '#f59e0b'
  return '#64748b'
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
    <div style={S.bar}>
      <span style={S.title}>vibe-quant</span>
      <div style={S.divider} />
      {isLive && <div style={S.liveBadge}>● LIVE</div>}
      <select
        style={S.select}
        value={selectedId ?? ''}
        onChange={(e) => onSelectSession(e.target.value)}
      >
        {sessions.map((s) => (
          <option key={s.session_id} value={s.session_id}>
            {s.session_id.slice(0, 8)}…{' '}
            {s.ended_at === null ? '(live)' : new Date(s.started_at).toLocaleDateString()}
          </option>
        ))}
      </select>
      <div style={S.stats}>
        {equity !== null && (
          <span>
            Equity{' '}
            <strong style={{ color: '#27ae60' }}>${equity.toFixed(2)}</strong>
          </span>
        )}
        {pnl !== null && (
          <span>
            P&amp;L{' '}
            <strong style={{ color: pnl >= 0 ? '#27ae60' : '#e74c3c' }}>
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
            </strong>
          </span>
        )}
        <span>
          Fills <strong style={{ color: '#e2e8f0' }}>{fillCount}</strong>
        </span>
        {isLive && (
          <span style={{ color: sseColor(sseStatus) }}>↻ {sseStatus}</span>
        )}
      </div>
    </div>
  )
}
