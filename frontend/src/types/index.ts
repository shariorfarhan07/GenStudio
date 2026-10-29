export type TaskKind =
  | 'image_to_image'
  | 'image_restyle'
  | 'text_to_image'
  | 'image_to_video'
  | 'text_to_video'
  | 'upscale_image'
  | 'upscale_video'
  | 'interpolate'

export interface PipelineTier {
  w?: number
  h?: number
  frames?: number
  vram_gb: number
}

export interface PipelineParam {
  type: 'text' | 'int' | 'float' | 'image' | 'video' | 'seed'
  required?: boolean
  default?: unknown
  min?: number
  max?: number
  multiple_of?: number
  rule?: string
  advanced?: boolean
  placeholder?: string
}

export interface Pipeline {
  id: string
  task: TaskKind
  label: string
  family: string
  description: string
  badges: string[]
  requires: string[]
  params: Record<string, PipelineParam>
  tiers: Record<string, PipelineTier>
  lora_points: { after: string; model_only: boolean }[]
  available: boolean
  unavailable_reason: string
}

export type JobStatus =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'postprocessing'
  | 'done'
  | 'failed'
  | 'cancelled'

export interface Job {
  id: string
  batch_id?: string
  pipeline_id: string
  task: string
  status: JobStatus
  progress: number
  eta_seconds?: number
  error?: string
  attempts: number
  priority: number
  created_at: string
  started_at?: string
  finished_at?: string
}

export interface Asset {
  id: string
  job_id?: string
  kind: 'image' | 'video'
  path: string
  thumb_path: string
  width?: number
  height?: number
  frames?: number
  fps?: number
  duration?: number
  seed?: number
  pipeline_id?: string
  prompt?: string
  favorite: boolean
  tags: string[]
  created_at: string
}

export interface Lora {
  id: string
  file: string
  display_name: string
  base_family: string
  trigger_words: string
  default_weight: number
  preview_path?: string
}

export interface ModelEntry {
  id: string
  filename: string
  label: string
  description: string
  pack: string
  folder: string
  size_gb: number
  license: string
  requires_token: boolean
  installed: boolean
  downloading: boolean
}

export interface SystemInfo {
  engine_status: 'stopped' | 'starting' | 'ready' | 'busy' | 'crashed'
  gpu: {
    name: string
    vram_total_mb: number
    vram_used_mb: number
    vram_free_mb: number
    utilization: number
    temperature: number
  }
  system: {
    ram_total_mb: number
    ram_used_mb: number
    ram_free_mb: number
    ram_percent: number
  }
  vram_warn_threshold_mb: number
}

export interface WsEvent {
  type: string
  data: Record<string, unknown>
}
