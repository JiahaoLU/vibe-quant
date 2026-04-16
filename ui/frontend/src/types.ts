export interface Session {
  session_id: string
  started_at: string
  ended_at: string | null
  mode: string
  strategy_names: string[]
}

export interface Snapshot {
  id: number
  session_id: string
  timestamp: string
  total_equity: number
  strategy_pnl: Record<string, number>
  strategy_equity: Record<string, number>
}

export interface Fill {
  id: number
  session_id: string
  order_id: string
  timestamp: string
  symbol: string
  direction: 'BUY' | 'SELL'
  quantity: number
  fill_price: number
  commission: number
}

export interface Order {
  id: number
  session_id: string
  order_id: string
  timestamp: string
  symbol: string
  direction: 'BUY' | 'SELL' | 'HOLD'
  quantity: number
  reference_price: number
}

export interface Signal {
  id: number
  session_id: string
  timestamp: string
  strategy_id: string
  symbol: string
  weight: number
}

export type SseStatus = 'connected' | 'reconnecting' | 'disconnected'
