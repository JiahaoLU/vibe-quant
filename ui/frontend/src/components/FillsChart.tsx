import Plot from 'react-plotly.js'
import type { Fill } from '../types'
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

interface FillsChartProps {
  fills: Fill[]
}

export function FillsChart({ fills }: FillsChartProps) {
  if (fills.length === 0) return (
    <ChartCard title="Fills" subtitle="▲ buy  ▼ sell">
      <EmptyState message="No fills" />
    </ChartCard>
  )

  const symbols = [...new Set(fills.map((f) => f.symbol))]

  const traces: Plotly.Data[] = symbols.flatMap((sym, i) => {
    const color = PALETTE[i % PALETTE.length]
    const symFills = fills.filter((f) => f.symbol === sym)
    const buys = symFills.filter((f) => f.direction === 'BUY')
    const sells = symFills.filter((f) => f.direction === 'SELL')
    return [
      {
        x: buys.map((f) => f.timestamp),
        y: buys.map((f) => f.fill_price),
        type: 'scatter' as const,
        mode: 'markers' as const,
        name: `${sym} buy`,
        marker: { symbol: 'triangle-up', size: 10, color },
      },
      {
        x: sells.map((f) => f.timestamp),
        y: sells.map((f) => f.fill_price),
        type: 'scatter' as const,
        mode: 'markers' as const,
        name: `${sym} sell`,
        marker: { symbol: 'triangle-down', size: 10, color, opacity: 0.6 },
      },
    ]
  })

  return (
    <ChartCard title="Fills" subtitle="▲ buy  ▼ sell">
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
