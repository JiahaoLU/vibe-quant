import Plot from 'react-plotly.js'
import type { Snapshot } from '../types'
import { DARK_LAYOUT_DATE, PALETTE, C } from '../theme'
import { ChartCard, EmptyState } from './ChartCard'

interface EquityChartProps {
  snapshots: Snapshot[]
}

export function EquityChart({ snapshots }: EquityChartProps) {
  if (snapshots.length === 0) return (
    <ChartCard title="Equity curve" subtitle="total + per-strategy">
      <EmptyState message="No equity data" />
    </ChartCard>
  )

  const times = snapshots.map((s) => s.timestamp)
  const strategyNames = Object.keys(snapshots[0].strategy_equity)

  const traces: Plotly.Data[] = [
    {
      x: times,
      y: snapshots.map((s) => s.total_equity),
      type: 'scatter',
      mode: 'lines',
      name: 'Total',
      line: { color: C.textBright, width: 2 },
    },
    ...strategyNames.map((name, i) => ({
      x: times,
      y: snapshots.map((s) => s.strategy_equity[name] ?? null),
      type: 'scatter' as const,
      mode: 'lines' as const,
      name,
      line: { color: PALETTE[i % PALETTE.length], width: 1.5, dash: 'dot' as const },
    })),
  ]

  return (
    <ChartCard title="Equity curve" subtitle="total + per-strategy">
      <Plot
        data={traces}
        layout={DARK_LAYOUT_DATE}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
