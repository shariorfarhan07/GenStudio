import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Wand2, Video, Image, Type, ChevronDown, ChevronUp, Play, Download, Star, Shuffle } from 'lucide-react'
import { clsx } from 'clsx'
import { api, mediaUrl, thumbUrl } from '../api/client'
import { useAppStore } from '../store'
import type { Pipeline, Asset, Lora } from '../types'

const TASK_TABS = [
  { id: 'image_to_image', label: 'Img → Img', icon: Image },
  { id: 'image_to_video', label: 'Img → Video', icon: Video },
  { id: 'text_to_image', label: 'Text → Img', icon: Type },
  { id: 'text_to_video', label: 'Text → Video', icon: Play },
] as const

type TabId = (typeof TASK_TABS)[number]['id']

export default function CreatePage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<TabId>('image_to_image')
  const [uploadId, setUploadId] = useState<string>('')
  const [uploadPreview, setUploadPreview] = useState<string>('')
  const [prompt, setPrompt] = useState('')
  const [negative, setNegative] = useState('')
  const [selectedPipeline, setSelectedPipeline] = useState<string>('')
  const [selectedTier, setSelectedTier] = useState<string>('')
  const [strength, setStrength] = useState(0.75)
  const [steps, setSteps] = useState<number | null>(null)
  const [seed, setSeed] = useState(-1)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectedLoras, setSelectedLoras] = useState<{ id: string; weight: number }[]>([])
  const [lastResult, setLastResult] = useState<Asset | null>(null)
  const [activeJobId, setActiveJobId] = useState<string>('')
  const fileRef = useRef<HTMLInputElement>(null)

  const { liveJobs } = useAppStore()
  const activeJob = activeJobId ? liveJobs[activeJobId] : null

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: api.pipelines.list })
  const { data: loras = [] } = useQuery({ queryKey: ['loras'], queryFn: () => api.loras.list() })

  const taskPipelines = pipelines.filter((p) => p.task === tab)
  const pipeline = pipelines.find((p) => p.id === selectedPipeline) ?? taskPipelines[0]
  const tiers = Object.entries(pipeline?.tiers ?? {})
  const tier = selectedTier || (tiers[0]?.[0] ?? '')

  // Auto-select first pipeline when tab changes
  const handleTabChange = (t: TabId) => {
    setTab(t)
    setSelectedPipeline('')
    setSelectedTier('')
  }

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploads.upload(file),
    onSuccess: (data, file) => {
      setUploadId(data.upload_id)
      setUploadPreview(URL.createObjectURL(file))
    },
  })

  const submitMutation = useMutation({
    mutationFn: async () => {
      const pid = pipeline?.id
      if (!pid) throw new Error('No pipeline selected')
      const params: Record<string, unknown> = {
        prompt,
        negative,
        seed,
        _upload_id: uploadId || undefined,
        _tier: tier,
        _loras: selectedLoras
          .map((sl) => {
            const l = loras.find((x) => x.id === sl.id)
            return l ? { file: l.file, weight: sl.weight } : null
          })
          .filter(Boolean),
      }
      if (steps !== null) params.steps = steps
      if (strength !== 0.75 && tab === 'image_to_image' && pipeline?.params?.strength) params.strength = strength
      return api.jobs.create({ pipeline_id: pid, params })
    },
    onSuccess: (data) => {
      const jid = data.job_ids[0]
      if (jid) setActiveJobId(jid)
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) uploadMutation.mutate(file)
  }, [uploadMutation])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
  }

  // Check if active job is done and load result
  const prevStatus = useRef<string>('')
  if (activeJob && activeJob.status === 'done' && prevStatus.current !== 'done') {
    prevStatus.current = 'done'
    api.assets.list({ page: 1 }).then((assets) => {
      const match = assets.find((a) => a.job_id === activeJobId)
      if (match) setLastResult(match)
    })
  }
  if (activeJob?.status && prevStatus.current === 'done' && activeJob.status !== 'done') {
    prevStatus.current = activeJob.status
  }

  const needsImage = tab === 'image_to_image' || tab === 'image_to_video'

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel */}
      <div className="w-[420px] shrink-0 flex flex-col border-r border-white/[0.06] overflow-y-auto">
        {/* Task tabs */}
        <div className="flex gap-0.5 p-3 bg-surface-1">
          {TASK_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => handleTabChange(id)}
              className={clsx(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-xs font-medium transition-colors',
                tab === id
                  ? 'bg-brand text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.05]',
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 p-4 space-y-4">
          {/* Image dropzone */}
          {needsImage && (
            <div>
              <label className="label">Input Image</label>
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileRef.current?.click()}
                className={clsx(
                  'relative border-2 border-dashed rounded-lg cursor-pointer transition-colors',
                  uploadPreview ? 'border-brand/50' : 'border-white/10 hover:border-white/20',
                )}
              >
                {uploadPreview ? (
                  <img src={uploadPreview} className="w-full h-40 object-cover rounded-lg" alt="input" />
                ) : (
                  <div className="h-32 flex flex-col items-center justify-center gap-2 text-gray-500">
                    <Upload className="w-8 h-8" />
                    <span className="text-sm">Drop image or click to upload</span>
                  </div>
                )}
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
              </div>
            </div>
          )}

          {/* Prompt */}
          <div>
            <label className="label">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={pipeline?.params?.prompt?.placeholder ?? 'Describe what you want…'}
              rows={3}
              className="input resize-none"
            />
          </div>

          {/* Model picker */}
          <div>
            <label className="label">Model</label>
            <div className="space-y-1.5">
              {taskPipelines.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSelectedPipeline(p.id)}
                  disabled={!p.available}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 rounded-lg border transition-colors',
                    selectedPipeline === p.id || (!selectedPipeline && p.id === taskPipelines[0]?.id)
                      ? 'border-brand/50 bg-brand/10'
                      : 'border-white/[0.06] bg-surface-2 hover:border-white/20',
                    !p.available && 'opacity-40',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{p.label}</span>
                    <div className="flex gap-1">
                      {p.badges.map((b) => (
                        <span key={b} className="badge bg-surface-3 text-gray-300">{b}</span>
                      ))}
                    </div>
                  </div>
                  {!p.available && (
                    <p className="text-xs text-danger/80 mt-0.5 truncate">{p.unavailable_reason}</p>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Resolution tier */}
          {tiers.length > 0 && (
            <div>
              <label className="label">Resolution</label>
              <div className="flex gap-2">
                {tiers.map(([name, t]) => (
                  <button
                    key={name}
                    onClick={() => setSelectedTier(name)}
                    className={clsx(
                      'flex-1 py-1.5 rounded text-xs font-medium border transition-colors',
                      tier === name ? 'bg-brand/20 border-brand/50 text-brand-light' : 'border-white/10 text-gray-400 hover:border-white/20',
                    )}
                  >
                    <div>{name}</div>
                    {t.w && t.h && <div className="text-gray-500">{t.w}×{t.h}</div>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Strength slider (I2I restyle) */}
          {tab === 'image_to_image' && pipeline?.params?.strength && (
            <div>
              <label className="label">Edit Strength <span className="text-gray-500">{strength.toFixed(2)}</span></label>
              <input
                type="range" min={0.1} max={1.0} step={0.05}
                value={strength} onChange={(e) => setStrength(parseFloat(e.target.value))}
                className="w-full accent-brand"
              />
            </div>
          )}

          {/* LoRA picker */}
          {loras.filter((l) => !pipeline?.family || l.base_family === '' || l.base_family === pipeline.family).length > 0 && (
            <div>
              <label className="label">LoRAs</label>
              <div className="space-y-1">
                {loras.slice(0, 5).map((l) => {
                  const sel = selectedLoras.find((x) => x.id === l.id)
                  return (
                    <div key={l.id} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!sel}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedLoras([...selectedLoras, { id: l.id, weight: l.default_weight }])
                          } else {
                            setSelectedLoras(selectedLoras.filter((x) => x.id !== l.id))
                          }
                        }}
                        className="accent-brand"
                      />
                      <span className="flex-1 text-sm text-gray-300">{l.display_name || l.file}</span>
                      {sel && (
                        <input
                          type="range" min={0} max={2} step={0.05}
                          value={sel.weight}
                          onChange={(e) =>
                            setSelectedLoras(selectedLoras.map((x) =>
                              x.id === l.id ? { ...x, weight: parseFloat(e.target.value) } : x,
                            ))
                          }
                          className="w-20 accent-brand"
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Advanced */}
          <div>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300"
            >
              {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              Advanced
            </button>
            {showAdvanced && (
              <div className="mt-3 space-y-3">
                <div>
                  <label className="label">Negative Prompt</label>
                  <textarea value={negative} onChange={(e) => setNegative(e.target.value)} rows={2} className="input resize-none" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label">Steps</label>
                    <input
                      type="number" min={1} max={100}
                      value={steps ?? (pipeline?.params?.steps?.default as number) ?? 20}
                      onChange={(e) => setSteps(parseInt(e.target.value))}
                      className="input"
                    />
                  </div>
                  <div>
                    <label className="label">Seed</label>
                    <div className="flex gap-1">
                      <input type="number" value={seed} onChange={(e) => setSeed(parseInt(e.target.value))} className="input" />
                      <button onClick={() => setSeed(-1)} className="btn-secondary px-2" title="Random">
                        <Shuffle className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Generate button */}
          <button
            onClick={() => submitMutation.mutate()}
            disabled={submitMutation.isPending || (needsImage && !uploadId)}
            className="btn-primary w-full py-3 text-base"
          >
            <Wand2 className="w-4 h-4" />
            {submitMutation.isPending ? 'Queuing…' : 'Generate'}
          </button>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col overflow-hidden bg-surface">
        {activeJob && activeJob.status !== 'done' && activeJob.status !== 'failed' && activeJob.status !== 'cancelled' && (
          <div className="p-4 border-b border-white/[0.06]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium capitalize">{activeJob.status}…</span>
              <span className="text-xs text-gray-500">
                {activeJob.progress}%
                {activeJob.eta_seconds ? ` · ${Math.ceil(activeJob.eta_seconds)}s left` : ''}
              </span>
            </div>
            <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand rounded-full transition-all duration-500"
                style={{ width: `${activeJob.progress}%` }}
              />
            </div>
          </div>
        )}

        {lastResult && (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-2xl mx-auto">
              {lastResult.kind === 'image' ? (
                <img
                  src={mediaUrl(lastResult.path)}
                  alt={lastResult.prompt ?? ''}
                  className="w-full rounded-lg"
                />
              ) : (
                <video
                  src={mediaUrl(lastResult.path)}
                  controls
                  autoPlay
                  loop
                  className="w-full rounded-lg"
                />
              )}

              {/* Action bar */}
              <div className="flex gap-2 mt-4 flex-wrap">
                {lastResult.kind === 'image' && (
                  <button
                    onClick={() => {
                      setUploadPreview(mediaUrl(lastResult.path))
                      // We'd need the actual bytes; skip for now, user can re-upload
                      setTab('image_to_video')
                    }}
                    className="btn-secondary"
                  >
                    <Video className="w-4 h-4" /> Animate this
                  </button>
                )}
                <button
                  onClick={() => api.assets.postprocess(lastResult.id, lastResult.kind === 'image' ? 'upscale_image' : 'upscale_video')}
                  className="btn-secondary"
                >
                  <Image className="w-4 h-4" /> Upscale
                </button>
                {lastResult.kind === 'video' && (
                  <button
                    onClick={() => api.assets.postprocess(lastResult.id, 'interpolate')}
                    className="btn-secondary"
                  >
                    Smooth (RIFE)
                  </button>
                )}
                <a href={mediaUrl(lastResult.path)} download className="btn-secondary">
                  <Download className="w-4 h-4" /> Download
                </a>
                <button
                  onClick={() => api.assets.update(lastResult.id, { favorite: !lastResult.favorite }).then((a) => setLastResult(a))}
                  className={clsx('btn-secondary', lastResult.favorite && 'text-warning')}
                >
                  <Star className="w-4 h-4" fill={lastResult.favorite ? 'currentColor' : 'none'} />
                </button>
              </div>

              {lastResult.prompt && (
                <p className="mt-3 text-xs text-gray-500 italic">"{lastResult.prompt}"</p>
              )}
            </div>
          </div>
        )}

        {!lastResult && !activeJob && (
          <div className="flex-1 flex items-center justify-center text-gray-600">
            <div className="text-center">
              <Wand2 className="w-16 h-16 mx-auto mb-3 opacity-20" />
              <p>Your generation will appear here</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
