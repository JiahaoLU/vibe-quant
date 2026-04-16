import type { Fill, Order } from '../types'

interface TradeSummaryProps {
  fills: Fill[]
  orders: Order[]
}

const card: React.CSSProperties = {
  background: '#0f0f1a',
  borderRadius: 4,
  padding: '10px 12px',
  textAlign: 'center',
}

function StatCard({ label, value, color = '#e2e8f0' }: { label: string; value: string; color?: string }) {
  return (
    <div style={card}>
      <div style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color, fontSize: 18, fontWeight: 700 }}>{value}</div>
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

  // Per-symbol breakdown
  const symbols = [...new Set(fills.map((f) => f.symbol))]
  const bySymbol = symbols.map((sym) => {
    const sf = fills.filter((f) => f.symbol === sym)
    const avgPrice = sf.reduce((s, f) => s + f.fill_price, 0) / sf.length
    const commission = sf.reduce((s, f) => s + f.commission, 0)
    return { sym, fills: sf.length, qty: sf.reduce((s, f) => s + f.quantity, 0), avgPrice, commission }
  })

  return (
    <div style={{ background: '#1a1a2e', borderRadius: 6, overflow: 'hidden' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #2a2a3e' }}>
        <span style={{ fontWeight: 600, color: '#e2e8f0' }}>Trade summary</span>
      </div>
      <div style={{ padding: '10px 12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 12 }}>
          <StatCard label="Fills" value={String(fills.length)} />
          <StatCard label="Buy / Sell" value={`${buyCount} / ${sellCount}`} />
          <StatCard label="Total qty" value={String(totalQty)} />
          <StatCard label="Commission" value={`$${totalCommission.toFixed(2)}`} color="#f59e0b" />
          <StatCard label="Avg slippage" value={`$${avgSlippage.toFixed(4)}`} color="#f59e0b" />
        </div>
        {bySymbol.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#94a3b8' }}>
            <thead>
              <tr style={{ color: '#64748b', borderBottom: '1px solid #2a2a3e' }}>
                {['Symbol', 'Fills', 'Qty', 'Avg price', 'Commission'].map((h) => (
                  <th key={h} style={{ textAlign: h === 'Symbol' ? 'left' : 'right', padding: '4px 8px', fontWeight: 500 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bySymbol.map((r) => (
                <tr key={r.sym} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '4px 8px' }}>{r.sym}</td>
                  <td style={{ textAlign: 'right', padding: '4px 8px' }}>{r.fills}</td>
                  <td style={{ textAlign: 'right', padding: '4px 8px' }}>{r.qty}</td>
                  <td style={{ textAlign: 'right', padding: '4px 8px' }}>${r.avgPrice.toFixed(2)}</td>
                  <td style={{ textAlign: 'right', padding: '4px 8px' }}>${r.commission.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
