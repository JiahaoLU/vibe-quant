import type { Fill, Order } from '../types'

interface TradeSummaryProps {
  fills: Fill[]
  orders: Order[]
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="stat-card">
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value" style={color ? { color } : undefined}>{value}</div>
    </div>
  )
}

export function TradeSummary({ fills, orders }: TradeSummaryProps) {
  const buyCount = fills.filter((f) => f.direction === 'BUY').length
  const sellCount = fills.filter((f) => f.direction === 'SELL').length
  const totalQty = fills.reduce((s, f) => s + f.quantity, 0)
  const totalCommission = fills.reduce((s, f) => s + f.commission, 0)

  const slippages = fills
    .map((f) => {
      const order = orders.find((o) => o.order_id === f.order_id)
      return order ? Math.abs(f.fill_price - order.reference_price) : null
    })
    .filter((s): s is number => s !== null)
  const avgSlippage =
    slippages.length > 0 ? slippages.reduce((a, b) => a + b, 0) / slippages.length : 0

  const symbols = [...new Set(fills.map((f) => f.symbol))]
  const bySymbol = symbols.map((sym) => {
    const sf = fills.filter((f) => f.symbol === sym)
    const avgPrice = sf.reduce((s, f) => s + f.fill_price, 0) / sf.length
    const commission = sf.reduce((s, f) => s + f.commission, 0)
    return { sym, fills: sf.length, qty: sf.reduce((s, f) => s + f.quantity, 0), avgPrice, commission }
  })

  return (
    <div className="glass" style={{ overflow: 'hidden' }}>
      <div className="chart-card__header">
        <span className="chart-card__title">Trade summary</span>
      </div>
      <div style={{ padding: '10px 12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 12 }}>
          <StatCard label="Fills" value={String(fills.length)} />
          <StatCard label="Buy / Sell" value={`${buyCount} / ${sellCount}`} />
          <StatCard label="Total qty" value={String(totalQty)} />
          <StatCard label="Commission" value={`$${totalCommission.toFixed(2)}`} color="var(--amber)" />
          <StatCard label="Avg slippage" value={`$${avgSlippage.toFixed(4)}`} color="var(--amber)" />
        </div>
        {bySymbol.length > 0 && (
          <table className="summary-table">
            <thead>
              <tr>
                {['Symbol', 'Fills', 'Qty', 'Avg price', 'Commission'].map((h) => (
                  <th key={h} style={{ textAlign: h === 'Symbol' ? 'left' : 'right' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bySymbol.map((r) => (
                <tr key={r.sym}>
                  <td>{r.sym}</td>
                  <td style={{ textAlign: 'right' }}>{r.fills}</td>
                  <td style={{ textAlign: 'right' }}>{r.qty}</td>
                  <td style={{ textAlign: 'right' }}>${r.avgPrice.toFixed(2)}</td>
                  <td style={{ textAlign: 'right' }}>${r.commission.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
