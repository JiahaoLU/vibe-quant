import { useEffect, useState } from 'react'
import './App.css'
import { fetchLiveSession, fetchSessions } from './api'
import { CommissionsChart } from './components/CommissionsChart'
import { EquityChart } from './components/EquityChart'
import { FillsChart } from './components/FillsChart'
import { Header } from './components/Header'
import { SignalHeatmap } from './components/SignalHeatmap'
import { TradeSummary } from './components/TradeSummary'
import { useSessionData } from './hooks/useSessionData'
import { useLiveSSE } from './hooks/useLiveSSE'
import type { Session } from './types'

const GRID2: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 16,
}

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [liveSessionId, setLiveSessionId] = useState<string | null>(null)

  // Load session list on mount
  useEffect(() => {
    Promise.all([fetchSessions(), fetchLiveSession()]).then(([all, live]) => {
      setSessions(all)
      const id = live ? live.session_id : all[0]?.session_id ?? null
      if (live) setLiveSessionId(live.session_id)
      setSelectedId(id)
    })
  }, [])

  const { snapshots, fills, orders, signals, loading, error, setSnapshots, setFills } =
    useSessionData(selectedId)

  const isLive = selectedId !== null && selectedId === liveSessionId

  const { status: sseStatus } = useLiveSSE(
    isLive ? selectedId : null,
    (newSnaps) => setSnapshots((prev) => [...prev, ...newSnaps]),
    (newFills) => setFills((prev) => [...prev, ...newFills]),
  )

  const lastSnap = snapshots.at(-1) ?? null
  const firstSnap = snapshots.at(0) ?? null
  const equity = lastSnap?.total_equity ?? null
  const pnl =
    equity !== null && firstSnap !== null ? equity - firstSnap.total_equity : null

  return (
    <>
      <Header
        sessions={sessions}
        selectedId={selectedId}
        liveSessionId={liveSessionId}
        onSelectSession={setSelectedId}
        equity={equity}
        pnl={pnl}
        fillCount={fills.length}
        sseStatus={sseStatus}
      />

      {error && (
        <div style={{ background: '#7f1d1d', color: '#fca5a5', padding: '8px 16px', fontSize: 13 }}>
          Error: {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
          Loading…
        </div>
      ) : (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <TradeSummary fills={fills} orders={orders} />
          <div style={GRID2}>
            <EquityChart snapshots={snapshots} />
            <FillsChart fills={fills} />
          </div>
          <div style={GRID2}>
            <SignalHeatmap signals={signals} />
            <CommissionsChart fills={fills} orders={orders} />
          </div>
        </div>
      )}
    </>
  )
}
