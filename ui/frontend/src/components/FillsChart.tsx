import Plot from 'react-plotly.js'
import type { Fill } from '../types'
import { DARK_LAYOUT_DATE, PALETTE } from '../theme'
import { ChartCard, EmptyState } from './ChartCard'

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
        layout={DARK_LAYOUT_DATE}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
