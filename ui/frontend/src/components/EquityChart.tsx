import Plot from 'react-plotly.js'
import type { Snapshot } from '../types'
import { ChartCard, EmptyState } from './ChartCard'

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: '#1a1a2e',
  plot_bgcolor: '#1a1a2e',
  font: { color: '#94a3b8', size: 11 },
  margin: { t: 10, r: 10, b: 40, l: 65 },
  xaxis: { gridcolor: '#2a2a3e', color: '#64748b', type: 'date' },
  yaxis: { gridcolor: '#2a2a3e', color: '#64748b' },
  legend: { bgcolor: 'transparent', font: { size: 10 } },
  height: 220,
}

const PALETTE = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

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
      line: { color: '#e2e8f0', width: 2 },
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
        layout={DARK_LAYOUT}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
