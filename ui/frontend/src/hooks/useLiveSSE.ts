import { useEffect, useState } from 'react'
import type { Fill, Snapshot, SseStatus } from '../types'

interface UseLiveSSEResult {
  status: SseStatus
}

export function useLiveSSE(
  sessionId: string | null,
  onSnapshots: (data: Snapshot[]) => void,
  onFills: (data: Fill[]) => void,
): UseLiveSSEResult {
  const [status, setStatus] = useState<SseStatus>('disconnected')

  useEffect(() => {
    if (!sessionId) {
      setStatus('disconnected')
      return
    }

    const es = new EventSource(`/api/sse?session_id=${sessionId}`)

    es.onopen = () => setStatus('connected')
    es.onerror = () => setStatus('reconnecting')

    es.onmessage = (e: MessageEvent<string>) => {
      const msg = JSON.parse(e.data) as
        | { type: 'snapshots'; data: Snapshot[] }
        | { type: 'fills'; data: Fill[] }
      if (msg.type === 'snapshots') onSnapshots(msg.data)
      if (msg.type === 'fills') onFills(msg.data)
    }

    return () => {
      es.close()
      setStatus('disconnected')
    }
  }, [sessionId])

  return { status }
}
