import { Package, Radio, TrendingUp } from 'lucide-react'
import type { ApiState } from '../types'

type OverviewProps = { state: ApiState }

function formatPrice(v: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2 }).format(v)
}

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'agora'
  if (mins < 60) return `${mins}min`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  return `${Math.floor(hrs / 24)}d`
}

function Overview({ state }: OverviewProps) {
  const { products, findings } = state
  const approvedFindings = findings.filter((f) => f.price_ok)
  const reviewFindings = findings.filter((f) => f.decision === 'review')
  const totalRuleTerms = products.reduce((acc, p) => acc + p.keywords.length, 0)

  const cards = [
    {
      label: 'Regras de Preço',
      value: products.length,
      sub: `${totalRuleTerms} termo${totalRuleTerms !== 1 ? 's' : ''}`,
      icon: Package,
      accent: 'text-haumea-400',
      bg: 'bg-haumea-600/8',
    },
    {
      label: 'Alertas / Revisão',
      value: findings.length,
      sub: `${reviewFindings.length} em revisão`,
      icon: Radio,
      accent: 'text-amber-400',
      bg: 'bg-amber-500/8',
    },
    {
      label: 'Dentro do Limite',
      value: approvedFindings.length,
      sub: findings.length > 0 ? `${Math.round((approvedFindings.length / findings.length) * 100)}% do total` : '—',
      icon: TrendingUp,
      accent: 'text-emerald-400',
      bg: 'bg-emerald-500/8',
    },
  ]

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-txt-primary tracking-tight">Visão Geral</h2>
        <p className="mt-1 text-sm text-txt-muted">Resumo do monitoramento em tempo real.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-lg border border-panel-border bg-panel-surface p-5 transition-colors hover:border-panel-hover"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">{c.label}</span>
              <div className={`flex h-8 w-8 items-center justify-center rounded-md ${c.bg}`}>
                <c.icon className={`h-4 w-4 ${c.accent}`} />
              </div>
            </div>
            <p className="mt-3 text-2xl font-bold tracking-tight text-txt-primary font-mono">{c.value}</p>
            <p className="mt-1 text-2xs text-txt-muted">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* products list */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-txt-primary">Regras Configuradas</h3>
        {products.length === 0 ? (
          <p className="rounded-lg border border-panel-border bg-panel-surface px-5 py-5 text-sm text-txt-muted">
            Nenhum produto cadastrado.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {products.map((p) => (
              <div
                key={p.id}
                className="flex items-start justify-between rounded-lg border border-panel-border bg-panel-surface px-4 py-3.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-1.5">
                    {p.keywords.map((kw) => (
                      <span
                        key={kw}
                        className="inline-flex items-center rounded bg-haumea-600/10 px-2 py-0.5 text-xs font-mono text-haumea-300"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1.5 text-2xs text-txt-muted font-mono">até {formatPrice(p.max_price)}</p>
                </div>
                <span className="ml-3 shrink-0 rounded bg-haumea-600/10 px-2 py-0.5 text-2xs font-medium text-haumea-400">
                  ativo
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* recent findings */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-txt-primary">Últimos Alertas</h3>
        {findings.length === 0 ? (
          <p className="rounded-lg border border-panel-border bg-panel-surface px-5 py-5 text-sm text-txt-muted">
            Nenhum alerta capturado ainda.
          </p>
        ) : (
          <div className="space-y-2">
            {findings.slice(0, 6).map((f) => (
              <div
                key={f.id}
                className="flex items-center gap-4 rounded-lg border border-panel-border bg-panel-surface px-4 py-3"
              >
                <div className={`h-2 w-2 shrink-0 rounded-full ${f.price_ok ? 'bg-haumea-400' : 'bg-txt-muted'}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="truncate text-sm text-txt-primary">{f.detected_title || f.product_title || f.product_keyword || '—'}</span>
                    <span className="shrink-0 text-2xs text-txt-muted">{f.source_group}</span>
                  </div>
                  {f.url && (
                    <a
                      href={f.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 block truncate text-2xs text-txt-muted hover:text-haumea-400 transition-colors"
                    >
                      {f.url}
                    </a>
                  )}
                </div>
                <div className="shrink-0 text-right">
                  {f.price_found !== null && (
                    <span className="text-sm font-mono font-medium text-txt-primary">{formatPrice(f.price_found)}</span>
                  )}
                  <p className="text-2xs text-txt-muted">{relativeTime(f.timestamp)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default Overview
