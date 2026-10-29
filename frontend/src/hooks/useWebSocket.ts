import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../store'
import { withToken } from '../api/client'
import type { SystemInfo } from '../types'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const qc = useQueryClient()
  const store = useAppStore()

  useEffect(() => {
    let ws: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(withToken(`${proto}://${location.host}/ws/events`))
      wsRef.current = ws

      ws.onopen = () => store.setWsConnected(true)
      ws.onclose = () => {
        store.setWsConnected(false)
        reconnectTimer = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()

      ws.onmessage = (ev) => {
        let msg: { type: string; data: Record<string, unknown> }
        try {
          msg = JSON.parse(ev.data)
        } catch {
          return
        }
        const { type, data } = msg

        if (type === 'stats') {
          store.setSystemInfo({
            engine_status: data.engine_status as SystemInfo['engine_status'],
            gpu: data.gpu as never,
            system: data.system as never,
            vram_warn_threshold_mb: (store.systemInfo?.vram_warn_threshold_mb ?? 11776),
          })
        } else if (type === 'job_queued' || type === 'job_updated') {
          const id = data.id as string
          store.updateLiveJob(id, data as never)
          if ((data.status as string) === 'done' || (data.status as string) === 'failed') {
            qc.invalidateQueries({ queryKey: ['jobs'] })
            qc.invalidateQueries({ queryKey: ['assets'] })
            setTimeout(() => store.removeLiveJob(id), 10_000)
          }
          // Update queue count
          qc.invalidateQueries({ queryKey: ['jobs', 'queued'] })
        } else if (type === 'download_progress') {
          store.setDownloadProgress(data.catalog_id as string, data.percent as number)
        } else if (type === 'download_done' || type === 'download_error' || type === 'download_cancelled') {
          store.clearDownloadProgress(data.catalog_id as string)
          qc.invalidateQueries({ queryKey: ['models'] })
        }
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      ws?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return wsRef
}
