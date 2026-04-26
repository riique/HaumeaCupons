import { RefreshCw, TerminalSquare } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { requestJson } from '../api'

export default function LogsPanel() {
  const [logs, setLogs] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  const fetchLogs = useCallback(async () => {
    try {
      const data = await requestJson<{ logs: string[] }>('/api/logs?lines=300')
      setLogs(data.logs)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchLogs()
    const id = setInterval(() => void fetchLogs(), 3000) // Poll every 3s
    return () => clearInterval(id)
  }, [fetchLogs])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  return (
    <section className="flex h-[calc(100vh-8rem)] flex-col space-y-4">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-lg font-semibold text-txt-primary tracking-tight">Logs do Sistema</h2>
          <p className="mt-1 text-sm text-txt-muted">Acompanhe a atividade do bot em tempo real.</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-txt-secondary cursor-pointer hover:text-txt-primary transition-colors">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded border-panel-border bg-panel-bg accent-haumea-600"
            />
            Auto-scroll
          </label>
          <button
            onClick={() => void fetchLogs()}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-panel-border px-3.5 text-sm text-txt-secondary transition hover:border-haumea-600 hover:text-haumea-400"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger shrink-0">
          {error}
        </div>
      ) : null}

      <div
        ref={scrollRef}
        className="flex-1 overflow-auto rounded-lg border border-panel-border bg-panel-surface p-4 font-mono text-xs leading-relaxed text-txt-secondary"
      >
        {logs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-txt-muted">
            <TerminalSquare className="mb-2 h-8 w-8 opacity-20" />
            <p>Nenhum log disponível.</p>
          </div>
        ) : (
          logs.map((line, i) => {
            // Very basic syntax highlighting for log levels
            let colorClass = 'text-txt-secondary'
            if (line.includes(' INFO ')) colorClass = 'text-haumea-400'
            else if (line.includes(' WARNING ') || line.includes(' WARN ')) colorClass = 'text-yellow-400'
            else if (line.includes(' ERROR ') || line.includes(' CRITICAL ')) colorClass = 'text-danger'

            return (
              <div key={i} className={`whitespace-pre-wrap break-all ${colorClass}`}>
                {line}
              </div>
            )
          })
        )}
      </div>
    </section>
  )
}
