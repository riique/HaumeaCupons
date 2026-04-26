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
    .map((group) => group.trim())
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
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-light text-ink">Grupos</h2>
        <p className="mt-1 text-sm font-light text-slate-400">Um grupo por linha, ou all para monitorar todos.</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <textarea
          className="min-h-36 w-full resize-y rounded-lg border border-gray-200 bg-white px-5 py-4 text-sm font-light leading-6 text-ink outline-none transition focus:border-action"
          name="chat_groups"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          disabled={disabled}
        />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button
          className="inline-flex h-11 items-center gap-2 rounded-lg border border-action px-4 text-sm font-light text-action transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
          type="submit"
          disabled={disabled}
        >
          <Save className="h-4 w-4" aria-hidden="true" />
          Salvar
        </button>
      </form>

      {groups.length > 0 ? (
        <div className="space-y-2">
          {groups.map((group) => (
            <div className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3" key={group}>
              <span className="min-w-0 truncate text-sm font-light text-slate-600">{group}</span>
              <button
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-100 text-slate-400 transition hover:border-gray-200 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
                onClick={() => setPendingDelete(group)}
                disabled={disabled}
                aria-label={`Excluir ${group}`}
                title="Excluir"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-gray-100 px-5 py-4 text-sm font-light text-slate-400">
          Monitorando todos os grupos.
        </p>
      )}

      {pendingDelete ? (
        <ConfirmDialog
          title="Excluir grupo"
          message={`Deseja excluir "${pendingDelete}" da lista monitorada?`}
          disabled={disabled}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const nextGroups = groups.filter((group) => group !== pendingDelete)
            const nextValue = nextGroups.length > 0 ? nextGroups.join('\n') : 'all'
            setValue(nextValue)
            onSave(nextValue)
            setPendingDelete(null)
          }}
        />
      ) : null}
    </section>
  )
}

export default ChatGroupsPanel
