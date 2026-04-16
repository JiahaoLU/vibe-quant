import Plot from 'react-plotly.js'
import type { Signal } from '../types'
import { ChartCard, EmptyState } from './ChartCard'

interface SignalHeatmapProps {
  signals: Signal[]
}

export function SignalHeatmap({ signals }: SignalHeatmapProps) {
  if (signals.length === 0) return (
    <ChartCard title="Signal weights" subtitle="green = long · red = short">
      <EmptyState message="No signals" />
    </ChartCard>
  )

  const symbols = [...new Set(signals.map((s) => s.symbol))].sort()
  const times = [...new Set(signals.map((s) => s.timestamp))].sort()

  // Build z matrix: rows = symbols, cols = times
  const z: (number | null)[][] = symbols.map((sym) =>
    times.map((t) => {
      const sig = signals.find((s) => s.symbol === sym && s.timestamp === t)
      return sig ? sig.weight : null
    }),
  )

  const height = Math.max(180, symbols.length * 32 + 60)

  const trace: Plotly.Data = {
    type: 'heatmap',
    x: times,
    y: symbols,
    z,
    colorscale: 'RdYlGn',
    zmin: -1,
    zmax: 1,
    showscale: true,
    colorbar: { thickness: 12, len: 0.8, tickfont: { size: 9, color: '#94a3b8' } },
  }

  const layout: Partial<Plotly.Layout> = {
    paper_bgcolor: '#1a1a2e',
    plot_bgcolor: '#1a1a2e',
    font: { color: '#94a3b8', size: 11 },
    margin: { t: 10, r: 60, b: 40, l: 65 },
    xaxis: { type: 'date', gridcolor: '#2a2a3e', color: '#64748b' },
    yaxis: { gridcolor: '#2a2a3e', color: '#64748b' },
    height,
  }

  return (
    <ChartCard title="Signal weights" subtitle="green = long · red = short">
      <Plot
        data={[trace]}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
