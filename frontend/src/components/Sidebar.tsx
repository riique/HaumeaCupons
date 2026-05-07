import { Activity, BarChart3, Menu, Package, Radio, X } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

type SidebarProps = {
  counts: {
    products: number
    findings: number
  }
}

const nav: { path: string; label: string; icon: typeof Activity }[] = [
  { path: '/geral', label: 'Visão Geral', icon: BarChart3 },
  { path: '/produtos', label: 'Produtos', icon: Package },
  { path: '/alertas', label: 'Alertas', icon: Radio },
]

function Sidebar({ counts }: SidebarProps) {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const pathname = location.pathname.replace(/\/+$/, '') || '/'

  const handleNav = (path: string) => {
    navigate(path)
    setOpen(false)
  }

  return (
    <>
      {/* mobile toggle */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed left-4 top-4 z-40 flex h-10 w-10 items-center justify-center rounded-md border border-panel-border bg-panel-surface text-txt-secondary lg:hidden"
        aria-label="Abrir menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        className={`fixed left-0 top-0 z-50 flex h-screen w-56 flex-col border-r border-panel-border bg-panel-surface transition-transform duration-200 ${
          open ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        <div className="flex items-center justify-between px-5 pt-7 pb-8">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-haumea-600">
              <span className="text-sm font-bold text-white">H</span>
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-txt-primary tracking-tight">
                HaumeaCupons
              </p>
              <p className="text-2xs text-txt-muted">Painel de Controle</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="flex h-7 w-7 items-center justify-center rounded text-txt-muted hover:text-txt-primary lg:hidden"
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 px-3">
          {nav.map(({ path, label, icon: Icon }) => {
            const isActive = path === '/geral'
              ? pathname === '/' || pathname === '/geral'
              : pathname === path
            return (
              <button
                key={path}
                type="button"
                onClick={() => handleNav(path)}
                aria-current={isActive ? 'page' : undefined}
                className={`group flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors ${
                  isActive
                    ? 'bg-haumea-600/10 text-haumea-400 font-medium'
                    : 'text-txt-secondary hover:bg-panel-hover hover:text-txt-primary'
                }`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 ${
                    isActive ? 'text-haumea-400' : 'text-txt-muted group-hover:text-txt-secondary'
                  }`}
                />
                {label}
              </button>
            )
          })}
        </nav>

        <div className="border-t border-panel-border px-5 py-4">
          <div className="space-y-2.5 text-2xs text-txt-muted">
            <div className="flex items-center justify-between">
              <span>Produtos</span>
              <span className="font-mono text-txt-secondary">{counts.products}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Alertas</span>
              <span className="font-mono text-txt-secondary">{counts.findings}</span>
            </div>
          </div>
        </div>

        <div className="border-t border-panel-border px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-haumea-400 animate-pulse-dot" />
            <span className="text-2xs text-haumea-400 font-medium">Painel online</span>
          </div>
        </div>
      </aside>
    </>
  )
}

export default Sidebar
