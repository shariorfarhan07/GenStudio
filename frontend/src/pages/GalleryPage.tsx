import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, Trash2, Download, Video, Image, Search } from 'lucide-react'
import { clsx } from 'clsx'
import { api, mediaUrl, thumbUrl } from '../api/client'
import type { Asset } from '../types'

export default function GalleryPage() {
  const qc = useQueryClient()
  const [kind, setKind] = useState<string>('')
  const [fav, setFav] = useState<boolean | undefined>(undefined)
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Asset | null>(null)

  const { data: assets = [] } = useQuery({
    queryKey: ['assets', kind, fav, q, page],
    queryFn: () => api.assets.list({ kind: kind || undefined, fav, q: q || undefined, page }),
    refetchInterval: 5000,
  })

  const favMut = useMutation({
    mutationFn: (a: Asset) => api.assets.update(a.id, { favorite: !a.favorite }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['assets'] }),
  })
  const delMut = useMutation({
    mutationFn: (id: string) => api.assets.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      setSelected(null)
    },
  })

  return (
    <div className="h-full flex overflow-hidden">
      {/* Main grid */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="p-4 flex items-center gap-3 border-b border-white/[0.06]">
          <div className="relative">
            <Search className="absolute left-2.5 top-2 w-4 h-4 text-gray-500" />
            <input
              value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search prompts…"
              className="input pl-8 w-48"
            />
          </div>
          <div className="flex gap-1">
            {[['', 'All'], ['image', 'Images'], ['video', 'Videos']].map(([v, l]) => (
              <button
                key={v} onClick={() => setKind(v)}
                className={clsx('px-3 py-1 rounded text-xs transition-colors',
                  kind === v ? 'bg-brand text-white' : 'bg-surface-3 text-gray-400 hover:text-gray-200')}
              >
                {l}
              </button>
            ))}
          </div>
          <button
            onClick={() => setFav(fav ? undefined : true)}
            className={clsx('flex items-center gap-1 px-3 py-1 rounded text-xs transition-colors',
              fav ? 'bg-warning/20 text-warning' : 'bg-surface-3 text-gray-400 hover:text-gray-200')}
          >
            <Star className="w-3.5 h-3.5" fill={fav ? 'currentColor' : 'none'} /> Favorites
          </button>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {assets.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-600">
              <div className="text-center">
                <Image className="w-16 h-16 mx-auto mb-3 opacity-20" />
                <p>No assets yet</p>
              </div>
            </div>
          ) : (
            <div className="columns-2 md:columns-3 lg:columns-4 gap-3 space-y-3">
              {assets.map((a) => (
                <AssetCard
                  key={a.id}
                  asset={a}
                  onClick={() => setSelected(a)}
                  onFav={() => favMut.mutate(a)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        <div className="flex justify-center gap-2 p-3 border-t border-white/[0.06]">
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="btn-secondary px-3">
            ←
          </button>
          <span className="flex items-center text-sm text-gray-400">Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={assets.length < 50} className="btn-secondary px-3">
            →
          </button>
        </div>
      </div>

      {/* Detail drawer */}
      {selected && (
        <div className="w-80 border-l border-white/[0.06] flex flex-col overflow-hidden">
          <div className="p-3 flex items-center justify-between border-b border-white/[0.06]">
            <span className="text-sm font-medium">Details</span>
            <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-200">✕</button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-4">
            {selected.kind === 'image' ? (
              <img src={mediaUrl(selected.path)} className="w-full rounded-lg" alt="" />
            ) : (
              <video src={mediaUrl(selected.path)} controls loop className="w-full rounded-lg" />
            )}

            <div className="space-y-2 text-xs">
              {selected.width && <Row label="Size" value={`${selected.width}×${selected.height}`} />}
              {selected.fps && <Row label="FPS" value={String(selected.fps)} />}
              {selected.duration && <Row label="Duration" value={`${selected.duration.toFixed(1)}s`} />}
              {selected.seed !== undefined && selected.seed !== null && <Row label="Seed" value={String(selected.seed)} />}
              {selected.pipeline_id && <Row label="Model" value={selected.pipeline_id} />}
              {selected.prompt && (
                <div>
                  <span className="text-gray-500">Prompt</span>
                  <p className="text-gray-300 mt-1 italic">"{selected.prompt}"</p>
                </div>
              )}
            </div>

            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => favMut.mutate(selected)}
                className={clsx('btn-secondary flex-1', selected.favorite && 'text-warning')}
              >
                <Star className="w-3.5 h-3.5" fill={selected.favorite ? 'currentColor' : 'none'} />
                {selected.favorite ? 'Unfav' : 'Favorite'}
              </button>
              <a href={mediaUrl(selected.path)} download className="btn-secondary flex-1 justify-center">
                <Download className="w-3.5 h-3.5" /> Save
              </a>
              <button
                onClick={() => delMut.mutate(selected.id)}
                className="btn-danger flex-1"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AssetCard({ asset, onClick, onFav }: { asset: Asset; onClick: () => void; onFav: () => void }) {
  return (
    <div
      className="relative group cursor-pointer rounded-lg overflow-hidden bg-surface-2 break-inside-avoid"
      onClick={onClick}
    >
      <img
        src={thumbUrl(asset.thumb_path) || mediaUrl(asset.path)}
        className="w-full object-cover"
        loading="lazy"
        alt=""
      />
      {asset.kind === 'video' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/10 transition-colors">
          <Video className="w-8 h-8 text-white opacity-80" />
        </div>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); onFav() }}
        className={clsx('absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded bg-black/50',
          asset.favorite && '!opacity-100 text-warning')}
      >
        <Star className="w-3.5 h-3.5" fill={asset.favorite ? 'currentColor' : 'none'} />
      </button>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-200">{value}</span>
    </div>
  )
}
