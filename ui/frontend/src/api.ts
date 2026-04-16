import type { Fill, Order, Session, Signal, Snapshot } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export const fetchSessions = () => get<Session[]>('/sessions')

export const fetchLiveSession = () =>
  get<Session>('/sessions/live').catch(() => null)

export const fetchSnapshots = (id: string) =>
  get<Snapshot[]>(`/sessions/${id}/snapshots`)

export const fetchFills = (id: string) =>
  get<Fill[]>(`/sessions/${id}/fills`)

export const fetchOrders = (id: string) =>
  get<Order[]>(`/sessions/${id}/orders`)

export const fetchSignals = (id: string) =>
  get<Signal[]>(`/sessions/${id}/signals`)
