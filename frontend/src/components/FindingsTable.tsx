import { Check, ExternalLink } from 'lucide-react'

import type { Finding } from '../types'

type FindingsTableProps = {
  findings: Finding[]
}

function formatTimestamp(value?: string) {
  if (!value) {
    return '-'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatPrice(value: Finding['price_found']) {
  if (value === null || value === undefined) {
    return '-'
  }

  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return String(value)
  }

  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 2,
  }).format(numeric)
}

function FindingsTable({ findings }: FindingsTableProps) {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-light text-ink">Últimos Alertas</h2>
        <p className="mt-1 text-sm font-light text-slate-400">Máximo de 200 registros recentes.</p>
      </div>

      {findings.length === 0 ? (
        <p className="rounded-lg border border-gray-100 px-5 py-6 text-sm font-light text-slate-400">
          Nenhum alerta encontrado
        </p>
      ) : (
        <div className="max-h-[520px] overflow-auto rounded-lg border border-gray-100 shadow-sm">
          <table className="min-w-[860px] divide-y divide-gray-100 text-left text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="text-xs font-light uppercase tracking-normal text-slate-400">
                <th className="px-5 py-4 font-light">Data</th>
                <th className="px-5 py-4 font-light">Grupo</th>
                <th className="px-5 py-4 font-light">Produto</th>
                <th className="px-5 py-4 font-light">Link</th>
                <th className="px-5 py-4 font-light">Preço</th>
                <th className="px-5 py-4 font-light">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {findings.map((finding) => (
                <tr className="align-top text-slate-500" key={finding.id}>
                  <td className="whitespace-nowrap px-5 py-4 font-light">
                    {formatTimestamp(finding.timestamp)}
                  </td>
                  <td className="max-w-40 px-5 py-4 font-light">
                    <span className="line-clamp-2">{finding.source_group || '-'}</span>
                  </td>
                  <td className="max-w-xs px-5 py-4 font-light">
                    <span className="line-clamp-2">{finding.product_keyword || '-'}</span>
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 font-light">
                    {finding.url ? (
                      <a
                        className="inline-flex items-center gap-2 text-action transition hover:text-blue-600"
                        href={finding.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        URL
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 font-light">
                    <span className="inline-flex items-center gap-2">
                      {finding.price_ok ? <Check className="h-4 w-4 text-green-500" aria-label="Preço aprovado" /> : null}
                      {formatPrice(finding.price_found)}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-light">{finding.price_ok ? 'Aprovado' : 'Fora da faixa'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default FindingsTable
