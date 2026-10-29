import type { Asset, Job, Lora, ModelEntry, Pipeline, SystemInfo } from '../types'

const BASE = ''

export function lanToken(): string {
  try {
    return localStorage.getItem('genstudio_lan_token') || ''
  } catch {
    return ''
  }
}

export function withToken(url: string): string {
  const t = lanToken()
  if (!t) return url
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(t)
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const token = lanToken()
  const r = await fetch(BASE + path, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts?.headers,
    },
    ...opts,
  })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(text || r.statusText)
  }
  return r.json() as Promise<T>
}

// ── System ─────────────────────────────────────────────────────────────────
export const api = {
  system: {
    get: () => req<SystemInfo>('/api/system'),
    restartEngine: () => req<{ ok: boolean }>('/api/system/engine/restart', { method: 'POST' }),
    engineLog: () => req<{ lines: string[] }>('/api/system/engine/log'),
  },

  // ── Pipelines ────────────────────────────────────────────────────────────
  pipelines: {
    list: () => req<Pipeline[]>('/api/pipelines'),
  },

  // ── Uploads ──────────────────────────────────────────────────────────────
  uploads: {
    upload: async (file: File): Promise<{ upload_id: string; filename: string }> => {
      const fd = new FormData()
      fd.append('file', file)
      const r = await fetch('/api/uploads', { method: 'POST', body: fd, headers: lanToken() ? { Authorization: `Bearer ${lanToken()}` } : {} })
      if (!r.ok) throw new Error(await r.text())
      return r.json()
    },
  },

  // ── Jobs ─────────────────────────────────────────────────────────────────
  jobs: {
    create: (body: { pipeline_id: string; params: Record<string, unknown>; batch?: Record<string, unknown> }) =>
      req<{ job_ids: string[] }>('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
    list: (status?: string) =>
      req<Job[]>('/api/jobs' + (status ? `?status=${status}` : '')),
    get: (id: string) => req<Job>(`/api/jobs/${id}`),
    cancel: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
    retry: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}/retry`, { method: 'POST' }),
    reorder: (ids: string[]) =>
      req<{ ok: boolean }>('/api/jobs/order', { method: 'PATCH', body: JSON.stringify({ ordered_ids: ids }) }),
  },

  // ── Assets ───────────────────────────────────────────────────────────────
  assets: {
    list: (params?: { kind?: string; pipeline_id?: string; fav?: boolean; q?: string; page?: number }) => {
      const p = new URLSearchParams()
      if (params?.kind) p.set('kind', params.kind)
      if (params?.pipeline_id) p.set('pipeline_id', params.pipeline_id)
      if (params?.fav !== undefined) p.set('fav', String(params.fav))
      if (params?.q) p.set('q', params.q)
      if (params?.page) p.set('page', String(params.page))
      return req<Asset[]>('/api/assets' + (p.toString() ? `?${p}` : ''))
    },
    get: (id: string) => req<Asset>(`/api/assets/${id}`),
    update: (id: string, body: { favorite?: boolean; tags?: string[] }) =>
      req<Asset>(`/api/assets/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id: string) => req<{ ok: boolean }>(`/api/assets/${id}`, { method: 'DELETE' }),
    postprocess: (id: string, op: string, options?: Record<string, unknown>) =>
      req<{ job_id: string }>(`/api/assets/${id}/postprocess`, {
        method: 'POST',
        body: JSON.stringify({ op, options: options ?? {} }),
      }),
  },

  // ── Models ───────────────────────────────────────────────────────────────
  models: {
    list: () => req<ModelEntry[]>('/api/models'),
    install: (id: string) => req<{ ok: boolean }>(`/api/models/${id}/install`, { method: 'POST' }),
    remove: (id: string) => req<{ ok: boolean }>(`/api/models/${id}`, { method: 'DELETE' }),
    cancel: (id: string) => req<{ ok: boolean }>(`/api/models/${id}/cancel`, { method: 'POST' }),
    disk: () => req<{ total_gb: number; used_gb: number; free_gb: number }>('/api/models/disk'),
  },

  // ── LoRAs ────────────────────────────────────────────────────────────────
  loras: {
    list: (family?: string) => req<Lora[]>('/api/loras' + (family ? `?family=${family}` : '')),
    rescan: () => req<{ added: number }>('/api/loras/rescan', { method: 'POST' }),
    update: (id: string, body: Partial<Lora>) =>
      req<Lora>(`/api/loras/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  },

  // ── Settings ─────────────────────────────────────────────────────────────
  settings: {
    get: () => req<Record<string, unknown>>('/api/settings'),
    update: (body: Record<string, unknown>) =>
      req<{ ok: boolean }>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
    generateToken: () => req<{ token: string }>('/api/settings/generate-lan-token', { method: 'POST' }),
  },
}

// ── Media URL helpers ─────────────────────────────────────────────────────
export function mediaUrl(path: string): string {
  // path is absolute on disk; convert to /media/... URL
  // outputs are under I:\AI\outputs\... served at /media/...
  const normalized = path.replace(/\\/g, '/').replace(/^.*\/outputs\//, '')
  return withToken(`/media/${normalized}`)
}

export function thumbUrl(thumbPath: string): string {
  if (!thumbPath) return ''
  const normalized = thumbPath.replace(/\\/g, '/').replace(/^.*\/outputs\//, '')
  return withToken(`/media/${normalized}`)
}
