import { useEffect, useState } from 'react'
import { fetchFills, fetchOrders, fetchSignals, fetchSnapshots } from '../api'
import type { Fill, Order, Signal, Snapshot } from '../types'

interface SessionData {
  snapshots: Snapshot[]
  fills: Fill[]
  orders: Order[]
  signals: Signal[]
  loading: boolean
  setSnapshots: React.Dispatch<React.SetStateAction<Snapshot[]>>
  setFills: React.Dispatch<React.SetStateAction<Fill[]>>
}

export function useSessionData(sessionId: string | null): SessionData {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [fills, setFills] = useState<Fill[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    setSnapshots([])
    setFills([])
    setOrders([])
    setSignals([])

    Promise.all([
      fetchSnapshots(sessionId),
      fetchFills(sessionId),
      fetchOrders(sessionId),
      fetchSignals(sessionId),
    ]).then(([snaps, f, o, sigs]) => {
      setSnapshots(snaps)
      setFills(f)
      setOrders(o)
      setSignals(sigs)
      setLoading(false)
    })
  }, [sessionId])

  return { snapshots, fills, orders, signals, loading, setSnapshots, setFills }
}
