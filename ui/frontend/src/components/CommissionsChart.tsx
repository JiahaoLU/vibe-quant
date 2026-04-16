import Plot from 'react-plotly.js'
import type { Fill, Order } from '../types'
import { ChartCard, EmptyState } from './ChartCard'

interface CommissionsChartProps {
  fills: Fill[]
  orders: Order[]
}

export function CommissionsChart({ fills, orders }: CommissionsChartProps) {
  if (fills.length === 0) return (
    <ChartCard title="Commissions & slippage">
      <EmptyState message="No fills" />
    </ChartCard>
  )

  const symbols = [...new Set(fills.map((f) => f.symbol))].sort()

  const commissions = symbols.map((sym) =>
    fills.filter((f) => f.symbol === sym).reduce((s, f) => s + f.commission, 0),
  )

  const slippages = symbols.map((sym) => {
    const symFills = fills.filter((f) => f.symbol === sym)
    const vals = symFills
      .map((f) => {
        const o = orders.find((ord) => ord.order_id === f.order_id)
        return o ? Math.abs(f.fill_price - o.reference_price) : null
      })
      .filter((v): v is number => v !== null)
    return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  })

  const traces: Plotly.Data[] = [
    {
      type: 'bar',
      name: 'Commission ($)',
      x: symbols,
      y: commissions,
      marker: { color: '#f59e0b' },
    },
    {
      type: 'bar',
      name: 'Avg slippage ($)',
      x: symbols,
      y: slippages,
      marker: { color: '#8b5cf6' },
    },
  ]

  const layout: Partial<Plotly.Layout> = {
    paper_bgcolor: '#1a1a2e',
    plot_bgcolor: '#1a1a2e',
    font: { color: '#94a3b8', size: 11 },
    margin: { t: 10, r: 10, b: 40, l: 65 },
    xaxis: { gridcolor: '#2a2a3e', color: '#64748b' },
    yaxis: { gridcolor: '#2a2a3e', color: '#64748b' },
    legend: { bgcolor: 'transparent', font: { size: 10 } },
    barmode: 'group',
    height: 220,
  }

  return (
    <ChartCard title="Commissions & slippage">
      <Plot
        data={traces}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
