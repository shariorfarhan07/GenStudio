import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, Trash2, X, CheckCircle, RefreshCw } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { ModelEntry } from '../types'

const PACKS = ['starter', 'quality', 'extra']

const PACK_COLORS: Record<string, string> = {
  starter: 'text-success',
  quality: 'text-brand-light',
  extra: 'text-warning',
}

export default function ModelsPage() {
  const qc = useQueryClient()
  const { downloadProgress } = useAppStore()
  const [pack, setPack] = useState<string>('')
  const [hfToken, setHfToken] = useState('')
  const [tokenSaved, setTokenSaved] = useState(false)

  const { data: models = [] } = useQuery({ queryKey: ['models'], queryFn: api.models.list })
  const { data: disk } = useQuery({ queryKey: ['disk'], queryFn: api.models.disk, refetchInterval: 10_000 })

  const installMut = useMutation({
    mutationFn: (id: string) => api.models.install(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  })
  const removeMut = useMutation({
    mutationFn: (id: string) => api.models.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  })
  const cancelMut = useMutation({
    mutationFn: (id: string) => api.models.cancel(id),
  })

  const saveToken = async () => {
    await api.settings.update({ hf_token: hfToken })
    setTokenSaved(true)
    setTimeout(() => setTokenSaved(false), 2000)
  }

  const filtered = pack ? models.filter((m) => m.pack === pack) : models

  return (
    <div className="h-full overflow-y-auto p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Models</h1>
        {disk && (
          <div className="text-xs text-gray-500">
            {disk.free_gb.toFixed(1)} GB free / {disk.total_gb.toFixed(1)} GB total
          </div>
        )}
      </div>

      {/* HF Token */}
      <div className="card p-4 mb-6">
        <label className="label">HuggingFace Token (required for Quality pack)</label>
        <div className="flex gap-2">
          <input
            type="password"
            value={hfToken}
            onChange={(e) => setHfToken(e.target.value)}
            placeholder="hf_…"
            className="input flex-1"
          />
          <button onClick={saveToken} className="btn-primary">
            {tokenSaved ? <CheckCircle className="w-4 h-4" /> : 'Save'}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Accept license at huggingface.co/black-forest-labs/FLUX.2-klein before installing Quality pack.
        </p>
      </div>

      {/* Pack filter */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setPack('')}
          className={clsx('px-3 py-1.5 rounded text-xs font-medium transition-colors',
            pack === '' ? 'bg-brand text-white' : 'bg-surface-3 text-gray-400 hover:text-gray-200')}
        >
          All
        </button>
        {PACKS.map((p) => (
          <button
            key={p}
            onClick={() => setPack(p)}
            className={clsx('px-3 py-1.5 rounded text-xs font-medium capitalize transition-colors',
              pack === p ? 'bg-brand text-white' : 'bg-surface-3 text-gray-400 hover:text-gray-200')}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {filtered.map((m) => (
          <ModelRow
            key={m.id}
            model={m}
            progress={downloadProgress[m.id]}
            onInstall={() => installMut.mutate(m.id)}
            onRemove={() => removeMut.mutate(m.id)}
            onCancel={() => cancelMut.mutate(m.id)}
          />
        ))}
      </div>
    </div>
  )
}

function ModelRow({
  model,
  progress,
  onInstall,
  onRemove,
  onCancel,
}: {
  model: ModelEntry
  progress?: number
  onInstall: () => void
  onRemove: () => void
  onCancel: () => void
}) {
  return (
    <div className="card p-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-sm font-medium">{model.label}</span>
          <span className={clsx('badge bg-surface-3', PACK_COLORS[model.pack] ?? 'text-gray-400')}>
            {model.pack}
          </span>
          {model.requires_token && (
            <span className="badge bg-warning/10 text-warning">Needs token</span>
          )}
        </div>
        <p className="text-xs text-gray-500 truncate">{model.description}</p>
        {model.downloading && progress !== undefined && (
          <div className="mt-1.5">
            <div className="h-1 bg-surface-3 rounded-full overflow-hidden">
              <div className="h-full bg-brand rounded-full transition-all" style={{ width: `${progress}%` }} />
            </div>
            <span className="text-xs text-gray-500">{progress}%</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-500">{model.size_gb.toFixed(1)} GB</span>
        {model.installed ? (
          <button onClick={onRemove} className="btn-secondary p-1.5 text-danger" title="Remove">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        ) : model.downloading ? (
          <button onClick={onCancel} className="btn-secondary p-1.5 text-danger" title="Cancel">
            <X className="w-3.5 h-3.5" />
          </button>
        ) : (
          <button onClick={onInstall} className="btn-secondary p-1.5" title="Download">
            <Download className="w-3.5 h-3.5" />
          </button>
        )}
        {model.installed && (
          <CheckCircle className="w-4 h-4 text-success" />
        )}
      </div>
    </div>
  )
}
