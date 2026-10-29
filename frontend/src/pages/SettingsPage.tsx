import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { CheckCircle, RefreshCw, Copy, RotateCcw } from 'lucide-react'
import { api } from '../api/client'

export default function SettingsPage() {
  const [form, setForm] = useState<Record<string, unknown>>({})
  const [saved, setSaved] = useState(false)
  const [log, setLog] = useState<string[]>([])

  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: api.settings.get })

  useEffect(() => {
    if (settings) setForm(settings)
  }, [settings])

  const saveMut = useMutation({
    mutationFn: () => api.settings.update(form),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  const tokenMut = useMutation({ mutationFn: api.settings.generateToken })
  const restartMut = useMutation({ mutationFn: api.system.restartEngine })

  const loadLog = async () => {
    const r = await api.system.engineLog()
    setLog(r.lines)
  }

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <div className="h-full overflow-y-auto p-6 max-w-2xl mx-auto space-y-8">
      <h1 className="text-xl font-semibold">Settings</h1>

      {/* Engine */}
      <section className="card p-5 space-y-4">
        <h2 className="text-sm font-medium text-gray-300">Engine</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Reserve VRAM (GB)</label>
            <input
              type="number" step={0.1} min={0} max={4}
              value={form.engine_reserve_vram as number ?? 0.6}
              onChange={(e) => set('engine_reserve_vram', parseFloat(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="label">Preview Method</label>
            <select
              value={form.engine_preview_method as string ?? 'auto'}
              onChange={(e) => set('engine_preview_method', e.target.value)}
              className="input"
            >
              {['auto', 'latent2rgb', 'taesd', 'none'].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="sage"
            checked={!!(form.engine_use_sage_attention)}
            onChange={(e) => set('engine_use_sage_attention', e.target.checked)}
            className="accent-brand"
          />
          <label htmlFor="sage" className="text-sm">Use SageAttention (faster, experimental on sm_120)</label>
        </div>
        <div className="flex gap-2">
          <button onClick={() => restartMut.mutate()} className="btn-secondary">
            <RotateCcw className="w-4 h-4" /> Restart Engine
          </button>
          <button onClick={loadLog} className="btn-secondary">View Engine Log</button>
        </div>
        {log.length > 0 && (
          <div className="bg-surface-3 rounded p-3 max-h-48 overflow-y-auto font-mono text-xs text-gray-400">
            {log.slice(-100).map((l, i) => <div key={i}>{l}</div>)}
          </div>
        )}
      </section>

      {/* Network */}
      <section className="card p-5 space-y-4">
        <h2 className="text-sm font-medium text-gray-300">Network</h2>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="lan"
            checked={!!(form.lan_access)}
            onChange={(e) => set('lan_access', e.target.checked)}
            className="accent-brand"
          />
          <label htmlFor="lan" className="text-sm">Enable LAN access (requires bearer token)</label>
        </div>
        {Boolean(form.lan_access) && (
          <div>
            <label className="label">LAN Token</label>
            <div className="flex gap-2">
              <input
                value={String(form.lan_token ?? '')}
                readOnly
                className="input font-mono text-xs"
              />
              <button
                onClick={() => tokenMut.mutate(undefined, { onSuccess: (d) => set('lan_token', d.token) })}
                className="btn-secondary shrink-0"
              >
                Generate
              </button>
              <button
                onClick={() => navigator.clipboard.writeText(String(form.lan_token ?? ''))}
                className="btn-secondary shrink-0"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Defaults */}
      <section className="card p-5 space-y-4">
        <h2 className="text-sm font-medium text-gray-300">Generation Defaults</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Default Steps</label>
            <input
              type="number" min={1} max={100}
              value={form.default_steps as number ?? 20}
              onChange={(e) => set('default_steps', parseInt(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="label">Default CFG</label>
            <input
              type="number" step={0.5} min={1} max={20}
              value={form.default_cfg as number ?? 7}
              onChange={(e) => set('default_cfg', parseFloat(e.target.value))}
              className="input"
            />
          </div>
        </div>
      </section>

      <button
        onClick={() => saveMut.mutate()}
        disabled={saveMut.isPending}
        className="btn-primary w-full py-3"
      >
        {saved ? <><CheckCircle className="w-4 h-4" /> Saved</> : 'Save Settings'}
      </button>
    </div>
  )
}
