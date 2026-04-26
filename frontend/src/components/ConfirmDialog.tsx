import { AlertTriangle, X } from 'lucide-react'

type ConfirmDialogProps = {
  title: string
  message: string
  confirmLabel?: string
  disabled?: boolean
  onCancel: () => void
  onConfirm: () => void
}

function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Excluir',
  disabled = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/30 px-4">
      <div
        className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-red-50 text-red-600">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
            <h3 id="confirm-title" className="text-base font-medium text-ink">
              {title}
            </h3>
          </div>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-400 transition hover:bg-gray-50 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            onClick={onCancel}
            disabled={disabled}
            aria-label="Cancelar"
            title="Cancelar"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <p className="mt-4 text-sm leading-6 text-slate-500">{message}</p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="inline-flex h-10 items-center justify-center rounded-md border border-gray-200 px-4 text-sm text-slate-600 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            onClick={onCancel}
            disabled={disabled}
          >
            Cancelar
          </button>
          <button
            className="inline-flex h-10 items-center justify-center rounded-md border border-red-600 bg-red-600 px-4 text-sm text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            onClick={onConfirm}
            disabled={disabled}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConfirmDialog
