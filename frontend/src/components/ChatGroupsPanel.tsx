import { Save, Trash2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'

import ConfirmDialog from './ConfirmDialog'

type ChatGroupsPanelProps = {
  chatGroups: string
  disabled: boolean
  onSave: (chatGroups: string) => void
}

function parseGroupLines(value: string) {
  const trimmed = value.trim()
  if (!trimmed || trimmed.toLowerCase() === 'all') {
    return []
  }
  return trimmed
    .replaceAll(',', '\n')
    .split('\n')
    .map((g) => g.trim())
    .filter(Boolean)
}

function ChatGroupsPanel({ chatGroups, disabled, onSave }: ChatGroupsPanelProps) {
  const [value, setValue] = useState(chatGroups)
  const [error, setError] = useState('')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  useEffect(() => {
    setValue(chatGroups)
  }, [chatGroups])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!value.trim()) {
      setError('Informe all ou pelo menos um grupo.')
      return
    }
    setError('')
    onSave(value)
  }

  const groups = parseGroupLines(value)

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-txt-primary tracking-tight">Grupos</h2>
        <p className="mt-1 text-sm text-txt-muted">
          Um grupo por linha, ou <code className="rounded bg-panel-raised px-1.5 py-0.5 font-mono text-2xs text-haumea-400">all</code> para monitorar todos.
        </p>
      </div>

      <form className="space-y-3" onSubmit={handleSubmit}>
        <textarea
          className="min-h-28 w-full resize-y rounded-md border border-panel-border bg-panel-bg px-4 py-3 text-sm font-mono text-txt-primary leading-6 outline-none transition placeholder:text-txt-muted focus:border-haumea-600"
          name="chat_groups"
          value={value}
          placeholder="all"
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          className="inline-flex h-9 items-center gap-2 rounded-md bg-haumea-600 px-4 text-sm font-medium text-white transition hover:bg-haumea-500 disabled:opacity-40"
          type="submit"
          disabled={disabled}
        >
          <Save className="h-3.5 w-3.5" />
          Salvar
        </button>
      </form>

      {groups.length > 0 ? (
        <div className="space-y-1.5">
          {groups.map((group) => (
            <div
              className="flex items-center justify-between rounded-md border border-panel-border bg-panel-surface px-4 py-2.5"
              key={group}
            >
              <span className="min-w-0 truncate text-sm font-mono text-txt-secondary">{group}</span>
              <button
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-txt-muted transition hover:bg-panel-hover hover:text-danger disabled:opacity-40"
                type="button"
                onClick={() => setPendingDelete(group)}
                disabled={disabled}
                title="Excluir"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-panel-border bg-panel-surface px-5 py-4 text-sm text-txt-muted">
          Monitorando todos os grupos.
        </p>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Excluir grupo"
          message={`Deseja excluir "${pendingDelete}" da lista monitorada?`}
          disabled={disabled}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const nextGroups = groups.filter((g) => g !== pendingDelete)
            const nextValue = nextGroups.length > 0 ? nextGroups.join('\n') : 'all'
            setValue(nextValue)
            onSave(nextValue)
            setPendingDelete(null)
          }}
        />
      )}
    </section>
  )
}

export default ChatGroupsPanel
