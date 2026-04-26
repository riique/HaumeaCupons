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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        className="w-full max-w-md rounded-lg border border-panel-border bg-panel-surface p-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-danger/10 text-danger">
              <AlertTriangle className="h-5 w-5" />
            </span>
            <h3 id="confirm-title" className="text-base font-semibold text-txt-primary">
              {title}
            </h3>
          </div>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-txt-muted transition hover:bg-panel-hover hover:text-txt-primary disabled:opacity-40"
            type="button"
            onClick={onCancel}
            disabled={disabled}
            title="Cancelar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-4 text-sm leading-6 text-txt-secondary">{message}</p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="inline-flex h-9 items-center justify-center rounded-md border border-panel-border px-4 text-sm text-txt-secondary transition hover:bg-panel-hover disabled:opacity-40"
            type="button"
            onClick={onCancel}
            disabled={disabled}
          >
            Cancelar
          </button>
          <button
            className="inline-flex h-9 items-center justify-center rounded-md bg-danger px-4 text-sm font-medium text-white transition hover:bg-danger/80 disabled:opacity-40"
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
