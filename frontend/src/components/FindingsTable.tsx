import { ExternalLink, FileText, Trash2, X } from 'lucide-react'
import { useState } from 'react'

import ConfirmDialog from './ConfirmDialog'
import type { Finding } from '../types'

type FindingsTableProps = {
  findings: Finding[]
  onDelete?: (id: number | string) => void
  onClearAll?: () => void
}

function formatTimestamp(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatPrice(value: Finding['price_found']) {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  if (Number.isNaN(n)) return String(value)
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2 }).format(n)
}

function FindingsTable({ findings, onDelete, onClearAll }: FindingsTableProps) {
  const [pendingDelete, setPendingDelete] = useState<Finding | null>(null)
  const [pendingClear, setPendingClear] = useState(false)
  const [originalFinding, setOriginalFinding] = useState<Finding | null>(null)
  const originalMessage = originalFinding?.raw_message?.trim()

  return (
    <section className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-txt-primary tracking-tight">Alertas</h2>
          <p className="mt-1 text-sm text-txt-muted">Últimos 200 registros capturados pelo bot.</p>
        </div>
        {findings.length > 0 && onClearAll && (
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-danger/30 px-3.5 text-sm text-danger transition hover:bg-danger/10 hover:border-danger"
            type="button"
            onClick={() => setPendingClear(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Limpar tudo
          </button>
        )}
      </div>

      {findings.length === 0 ? (
        <p className="rounded-lg border border-panel-border bg-panel-surface px-5 py-6 text-sm text-txt-muted">
          Nenhum alerta encontrado.
        </p>
      ) : (
        <div className="overflow-auto rounded-lg border border-panel-border">
          <table className="min-w-[960px] w-full text-left text-sm">
            <thead>
              <tr className="border-b border-panel-border bg-panel-surface">
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Data</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Grupo</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Produto</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Cupons</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Link</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Preço</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Status</th>
                <th className="px-4 py-3 text-2xs font-semibold uppercase tracking-wide text-txt-muted">Original</th>
                <th className="w-12 px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-panel-border">
              {findings.map((f) => (
                <tr key={f.id} className="transition-colors hover:bg-panel-surface/60">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-2xs text-txt-secondary">
                    {formatTimestamp(f.timestamp)}
                  </td>
                  <td className="max-w-36 px-4 py-3">
                    <span className="line-clamp-1 text-sm text-txt-secondary">{f.source_group || '—'}</span>
                  </td>
                  <td className="max-w-xs px-4 py-3">
                    <span className="line-clamp-1 text-sm text-txt-primary">{f.product_keyword || '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    {f.coupons && f.coupons.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {f.coupons.map((c) => (
                          <span key={c} className="rounded bg-amber-500/10 px-1.5 py-0.5 text-2xs font-mono text-amber-400">
                            {c}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-2xs text-txt-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {f.links && f.links.length > 0 ? (
                      <div className="space-y-0.5">
                        {f.links.map((url, i) => (
                          <a
                            key={i}
                            className="flex items-center gap-1 text-sm text-haumea-400 transition hover:text-haumea-300"
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <span className="max-w-48 truncate">{url.replace(/^https?:\/\//, '')}</span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        ))}
                      </div>
                    ) : f.url ? (
                      <a
                        className="inline-flex items-center gap-1.5 text-sm text-haumea-400 transition hover:text-haumea-300"
                        href={f.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Abrir
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-sm text-txt-primary">
                    {formatPrice(f.price_found)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-2xs font-medium ${
                        f.price_ok
                          ? 'bg-haumea-600/10 text-haumea-400'
                          : 'bg-panel-hover text-txt-muted'
                      }`}
                    >
                      {f.price_ok ? 'Aprovado' : 'Fora da faixa'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {f.raw_message?.trim() ? (
                      <button
                        className="inline-flex h-8 items-center gap-1.5 rounded-md border border-panel-border px-2.5 text-2xs font-medium text-txt-secondary transition hover:bg-panel-hover hover:text-txt-primary"
                        type="button"
                        onClick={() => setOriginalFinding(f)}
                      >
                        <FileText className="h-3.5 w-3.5" />
                        Ver original
                      </button>
                    ) : (
                      <span className="text-2xs text-txt-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {onDelete && (
                      <button
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-txt-muted transition hover:bg-panel-hover hover:text-danger"
                        type="button"
                        onClick={() => setPendingDelete(f)}
                        title="Excluir"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pendingDelete && onDelete && (
        <ConfirmDialog
          title="Excluir alerta"
          message={`Deseja excluir o alerta de "${pendingDelete.product_keyword || 'sem keyword'}"?`}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => { onDelete(pendingDelete.id); setPendingDelete(null) }}
        />
      )}

      {pendingClear && onClearAll && (
        <ConfirmDialog
          title="Limpar todos os alertas"
          message={`Tem certeza que deseja excluir todos os ${findings.length} alertas? Esta ação não pode ser desfeita.`}
          onCancel={() => setPendingClear(false)}
          onConfirm={() => { onClearAll(); setPendingClear(false) }}
        />
      )}

      {originalFinding && originalMessage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          onClick={() => setOriginalFinding(null)}
        >
          <div
            className="w-full max-w-2xl rounded-lg border border-panel-border bg-panel-surface p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="original-message-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-haumea-600/10 text-haumea-400">
                  <FileText className="h-5 w-5" />
                </span>
                <h3 id="original-message-title" className="text-base font-semibold text-txt-primary">
                  Mensagem original
                </h3>
              </div>
              <button
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-txt-muted transition hover:bg-panel-hover hover:text-txt-primary"
                type="button"
                onClick={() => setOriginalFinding(null)}
                title="Fechar"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 max-h-[60vh] overflow-auto rounded-md border border-panel-border bg-panel-bg p-4">
              <p className="whitespace-pre-wrap break-words text-sm leading-6 text-txt-secondary">
                {originalFinding.raw_message}
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default FindingsTable
