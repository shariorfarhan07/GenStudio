import { create } from 'zustand'
import type { Job, SystemInfo, WsEvent } from '../types'

interface AppStore {
  // System / engine status
  systemInfo: SystemInfo | null
  setSystemInfo: (info: SystemInfo) => void

  // WebSocket connection
  wsConnected: boolean
  setWsConnected: (v: boolean) => void

  // Jobs running in the current session (for live progress)
  liveJobs: Record<string, Job>
  updateLiveJob: (id: string, patch: Partial<Job>) => void
  removeLiveJob: (id: string) => void

  // Latest preview image (base64 or blob URL)
  latentPreview: string | null
  setLatentPreview: (url: string | null) => void

  // Queue count badge
  queueCount: number
  setQueueCount: (n: number) => void

  // Download progress: catalog_id -> percent
  downloadProgress: Record<string, number>
  setDownloadProgress: (id: string, pct: number) => void
  clearDownloadProgress: (id: string) => void
}

export const useAppStore = create<AppStore>((set) => ({
  systemInfo: null,
  setSystemInfo: (info) => set({ systemInfo: info }),

  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),

  liveJobs: {},
  updateLiveJob: (id, patch) =>
    set((s) => ({
      liveJobs: { ...s.liveJobs, [id]: { ...(s.liveJobs[id] ?? {}), ...patch } as Job },
    })),
  removeLiveJob: (id) =>
    set((s) => {
      const lj = { ...s.liveJobs }
      delete lj[id]
      return { liveJobs: lj }
    }),

  latentPreview: null,
  setLatentPreview: (url) => set({ latentPreview: url }),

  queueCount: 0,
  setQueueCount: (n) => set({ queueCount: n }),

  downloadProgress: {},
  setDownloadProgress: (id, pct) =>
    set((s) => ({ downloadProgress: { ...s.downloadProgress, [id]: pct } })),
  clearDownloadProgress: (id) =>
    set((s) => {
      const dp = { ...s.downloadProgress }
      delete dp[id]
      return { downloadProgress: dp }
    }),
}))
