import Plot from 'react-plotly.js'
import type { Signal } from '../types'
import { DARK_LAYOUT, C } from '../theme'
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

  const z: (number | null)[][] = symbols.map((sym) =>
    times.map((t) => {
      const sig = signals.find((s) => s.symbol === sym && s.timestamp === t)
      return sig ? sig.weight : null
    }),
  )

  const trace: Plotly.Data = {
    type: 'heatmap',
    x: times,
    y: symbols,
    z,
    colorscale: [
      [0,   C.red],
      [0.5, '#1a1e2e'],
      [1,   C.green],
    ],
    zmin: -1,
    zmax: 1,
    showscale: true,
    colorbar: {
      thickness: 10,
      len: 0.8,
      tickfont: { size: 9, color: C.text },
      outlinewidth: 0,
    },
  }

  const layout: Partial<Plotly.Layout> = {
    ...DARK_LAYOUT,
    xaxis: { ...DARK_LAYOUT.xaxis, type: 'date' },
    margin: { t: 10, r: 60, b: 40, l: 65 },
  }

  return (
    <ChartCard title="Signal weights" subtitle="green = long · red = short">
      <Plot
        data={[trace]}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
