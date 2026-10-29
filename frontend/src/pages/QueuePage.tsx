import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, RotateCcw, ChevronUp, ChevronDown } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { Job } from '../types'

const STATUS_COLORS: Record<string, string> = {
  queued: 'text-gray-400',
  preparing: 'text-accent',
  running: 'text-warning',
  postprocessing: 'text-brand-light',
  done: 'text-success',
  failed: 'text-danger',
  cancelled: 'text-gray-500',
}

function JobRow({ job }: { job: Job }) {
  const { liveJobs } = useAppStore()
  const live = liveJobs[job.id]
  const status = live?.status ?? job.status
  const progress = live?.progress ?? job.progress
  const qc = useQueryClient()

  const cancelMut = useMutation({
    mutationFn: () => api.jobs.cancel(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
  const retryMut = useMutation({
    mutationFn: () => api.jobs.retry(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  return (
    <div className="card p-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={clsx('text-xs font-medium capitalize', STATUS_COLORS[status])}>{status}</span>
          <span className="text-xs text-gray-500 truncate">{job.pipeline_id}</span>
        </div>
        {(status === 'running' || status === 'preparing') && (
          <div className="h-1 bg-surface-3 rounded-full overflow-hidden w-full">
            <div
              className="h-full bg-brand rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
        {job.error && <p className="text-xs text-danger mt-1 truncate">{job.error}</p>}
      </div>
      <div className="flex gap-1 shrink-0">
        {['failed', 'cancelled'].includes(status) && (
          <button onClick={() => retryMut.mutate()} className="btn-secondary p-1.5" title="Retry">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        )}
        {['queued', 'preparing', 'running'].includes(status) && (
          <button onClick={() => cancelMut.mutate()} className="btn-secondary p-1.5 text-danger" title="Cancel">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

export default function QueuePage() {
  const { data: jobs = [] } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => api.jobs.list(),
    refetchInterval: 3000,
  })

  const active = jobs.filter((j) => ['queued', 'preparing', 'running', 'postprocessing'].includes(j.status))
  const finished = jobs.filter((j) => ['done', 'failed', 'cancelled'].includes(j.status)).slice(0, 20)

  return (
    <div className="h-full overflow-y-auto p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Queue</h1>

      {active.length === 0 && (
        <div className="card p-6 text-center text-gray-500 mb-6">No active jobs</div>
      )}
      <div className="space-y-2 mb-8">
        {active.map((j) => <JobRow key={j.id} job={j} />)}
      </div>

      {finished.length > 0 && (
        <>
          <h2 className="text-sm font-medium text-gray-400 mb-3">Recent</h2>
          <div className="space-y-2">
            {finished.map((j) => <JobRow key={j.id} job={j} />)}
          </div>
        </>
      )}
    </div>
  )
}
