import Plot from 'react-plotly.js'
import type { Fill, Order } from '../types'
import { DARK_LAYOUT, C } from '../theme'
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
      marker: { color: C.amber },
    },
    {
      type: 'bar',
      name: 'Avg slippage ($)',
      x: symbols,
      y: slippages,
      marker: { color: C.purple },
    },
  ]

  const layout: Partial<Plotly.Layout> = {
    ...DARK_LAYOUT,
    barmode: 'group',
  }

  return (
    <ChartCard title="Commissions & slippage">
      <Plot
        data={traces}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </ChartCard>
  )
}
