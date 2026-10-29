import { NavLink } from 'react-router-dom'
import { Wand2, ListVideo, Image, Database, Settings, Wifi, WifiOff, Zap } from 'lucide-react'
import { useAppStore } from '../store'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { clsx } from 'clsx'

const nav = [
  { to: '/', icon: Wand2, label: 'Create' },
  { to: '/queue', icon: ListVideo, label: 'Queue' },
  { to: '/gallery', icon: Image, label: 'Gallery' },
  { to: '/models', icon: Database, label: 'Models' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ready: 'bg-success',
    busy: 'bg-warning animate-pulse',
    starting: 'bg-accent animate-pulse',
    crashed: 'bg-danger',
    stopped: 'bg-gray-500',
  }
  return <span className={clsx('inline-block w-2 h-2 rounded-full', colors[status] ?? 'bg-gray-500')} />
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { systemInfo, wsConnected, queueCount } = useAppStore()

  // Initial fetch if WS hasn't fired yet
  useQuery({
    queryKey: ['system'],
    queryFn: api.system.get,
    refetchInterval: 5000,
  })

  const gpu = systemInfo?.gpu
  const sys = systemInfo?.system
  const engStatus = systemInfo?.engine_status ?? 'stopped'

  const vramPct = gpu ? Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100) : 0
  const ramPct = sys ? sys.ram_percent : 0

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-gray-100">
      {/* Sidebar */}
      <aside className="w-14 flex flex-col items-center py-4 gap-1 bg-surface-1 border-r border-white/[0.06] shrink-0">
        {/* Logo */}
        <div className="mb-4 p-1">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand to-accent flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
        </div>

        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            title={label}
            className={({ isActive }) =>
              clsx(
                'relative w-10 h-10 flex items-center justify-center rounded-lg transition-colors',
                isActive
                  ? 'bg-brand/20 text-brand-light'
                  : 'text-gray-500 hover:text-gray-200 hover:bg-white/[0.05]',
              )
            }
          >
            <Icon className="w-5 h-5" />
            {to === '/queue' && queueCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-brand rounded-full text-[10px] flex items-center justify-center text-white font-bold">
                {queueCount > 9 ? '9+' : queueCount}
              </span>
            )}
          </NavLink>
        ))}
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Status bar */}
        <header className="h-9 flex items-center px-4 gap-4 bg-surface-1 border-b border-white/[0.06] shrink-0 text-xs text-gray-400">
          <div className="flex items-center gap-1.5">
            <StatusDot status={engStatus} />
            <span className="capitalize">{engStatus}</span>
          </div>

          {gpu && (
            <>
              <div className="flex items-center gap-1.5">
                <span>VRAM</span>
                <div className="w-16 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={clsx('h-full rounded-full transition-all', vramPct > 90 ? 'bg-danger' : vramPct > 75 ? 'bg-warning' : 'bg-brand')}
                    style={{ width: `${vramPct}%` }}
                  />
                </div>
                <span>{gpu.vram_used_mb > 1024 ? `${(gpu.vram_used_mb / 1024).toFixed(1)}G` : `${gpu.vram_used_mb}M`}</span>
              </div>

              <div className="flex items-center gap-1.5">
                <span>RAM</span>
                <div className="w-16 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={clsx('h-full rounded-full transition-all', ramPct > 90 ? 'bg-danger' : 'bg-accent')}
                    style={{ width: `${ramPct}%` }}
                  />
                </div>
                <span>{sys ? `${(sys.ram_used_mb / 1024).toFixed(1)}G` : '—'}</span>
              </div>

              {gpu.temperature > 0 && (
                <span className={clsx(gpu.temperature > 85 ? 'text-danger' : '')}>{gpu.temperature}°C</span>
              )}
            </>
          )}

          <div className="ml-auto flex items-center gap-1.5">
            {wsConnected ? (
              <Wifi className="w-3.5 h-3.5 text-success" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-danger" />
            )}
            <span className="text-gray-600">GenStudio</span>
          </div>
        </header>

        {/* Page */}
        <div className="flex-1 overflow-hidden">
          {children}
        </div>
      </main>
    </div>
  )
}
