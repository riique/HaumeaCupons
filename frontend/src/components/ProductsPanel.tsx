import { Check, Edit3, Plus, Trash2, X } from 'lucide-react'
import { type FormEvent, useCallback, useRef, useState } from 'react'

import ConfirmDialog from './ConfirmDialog'
import type { Product, ProductPayload } from '../types'

type ProductsPanelProps = {
  products: Product[]
  disabled: boolean
  onAdd: (product: ProductPayload) => void
  onDelete: (id: number) => void
  onEdit: (id: number, product: ProductPayload) => void
}

type ProductFormProps = {
  disabled: boolean
  initialValue?: ProductPayload
  submitLabel: string
  onCancel?: () => void
  onSubmit: (product: ProductPayload) => void
}

const emptyProduct: ProductPayload = { keywords: [], max_price: 0 }

function formatPrice(value: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2 }).format(value)
}

const inputCls =
  'w-full rounded-md border border-panel-border bg-panel-bg px-3 py-2.5 text-sm text-txt-primary outline-none transition placeholder:text-txt-muted focus:border-haumea-600 font-mono'

// ── keyword tag input ────────────────────────────────────────────────────────
function KeywordInput({
  value,
  onChange,
  disabled,
}: {
  value: string[]
  onChange: (next: string[]) => void
  disabled: boolean
}) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const commit = useCallback(() => {
    const trimmed = draft.trim().toLowerCase()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setDraft('')
  }, [draft, value, onChange])

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
      e.preventDefault()
      commit()
    }
    if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  const remove = (kw: string) => onChange(value.filter((k) => k !== kw))

  return (
    <div
      className="flex min-h-[42px] w-full flex-wrap gap-1.5 rounded-md border border-panel-border bg-panel-bg px-2.5 py-1.5 cursor-text transition focus-within:border-haumea-600"
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((kw) => (
        <span
          key={kw}
          className="inline-flex items-center gap-1 rounded bg-haumea-600/15 px-2 py-0.5 text-xs font-mono text-haumea-300"
        >
          {kw}
          {!disabled && (
            <button type="button" onClick={() => remove(kw)} className="hover:text-danger transition-colors" tabIndex={-1}>
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKey}
        onBlur={commit}
        disabled={disabled}
        placeholder={value.length === 0 ? 'iphone, celular… (Enter ou vírgula)' : ''}
        className="min-w-24 flex-1 bg-transparent text-sm text-txt-primary outline-none placeholder:text-txt-muted font-mono"
      />
    </div>
  )
}

// ── form ─────────────────────────────────────────────────────────────────────
function ProductForm({ disabled, initialValue = emptyProduct, submitLabel, onCancel, onSubmit }: ProductFormProps) {
  const [keywords, setKeywords] = useState<string[]>(initialValue.keywords)
  const [maxPrice, setMaxPrice] = useState(String(initialValue.max_price))
  const [error, setError] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const max = Number(maxPrice)
    if (keywords.length === 0) { setError('Informe ao menos uma palavra-chave.'); return }
    if (!Number.isFinite(max) || max < 0) { setError('Informe um preço máximo válido.'); return }
    setError('')
    onSubmit({ keywords, max_price: max })
  }

  return (
    <form
      className="grid gap-3 rounded-lg border border-panel-border bg-panel-surface p-4 sm:grid-cols-[1fr_160px_auto]"
      onSubmit={handleSubmit}
    >
      <label className="space-y-1.5">
        <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Palavras-chave</span>
        <KeywordInput value={keywords} onChange={setKeywords} disabled={disabled} />
      </label>
      <label className="space-y-1.5">
        <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Preço máx (R$)</span>
        <input
          className={inputCls}
          name="max_price"
          required
          min="0"
          step="0.01"
          type="number"
          placeholder="500"
          value={maxPrice}
          onChange={(e) => setMaxPrice(e.target.value)}
          disabled={disabled}
        />
      </label>
      <div className="flex items-end gap-2">
        <button
          className="inline-flex h-[42px] items-center gap-2 rounded-md bg-haumea-600 px-4 text-sm font-medium text-white transition hover:bg-haumea-500 disabled:opacity-40"
          type="submit"
          disabled={disabled}
        >
          <Check className="h-4 w-4" />
          {submitLabel}
        </button>
        {onCancel && (
          <button
            className="inline-flex h-[42px] w-[42px] items-center justify-center rounded-md border border-panel-border text-txt-muted transition hover:text-txt-primary hover:border-panel-hover disabled:opacity-40"
            type="button"
            onClick={onCancel}
            disabled={disabled}
            title="Cancelar"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {error && <p className="text-sm text-danger sm:col-span-3">{error}</p>}
    </form>
  )
}

// ── panel ─────────────────────────────────────────────────────────────────────
function ProductsPanel({ products, disabled, onAdd, onDelete, onEdit }: ProductsPanelProps) {
  const [isAdding, setIsAdding] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Product | null>(null)

  const handleAdd = (p: ProductPayload) => { onAdd(p); setIsAdding(false) }
  const handleEdit = (id: number, p: ProductPayload) => { onEdit(id, p); setEditingId(null) }

  return (
    <section className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-txt-primary tracking-tight">Produtos</h2>
          <p className="mt-1 text-sm text-txt-muted">
            Palavras-chave e preço máximo monitorados pelo bot.
          </p>
        </div>
        <button
          className="inline-flex h-9 items-center gap-2 rounded-md border border-panel-border px-3.5 text-sm text-txt-secondary transition hover:border-haumea-600 hover:text-haumea-400 disabled:opacity-40"
          type="button"
          onClick={() => { setIsAdding((c) => !c); setEditingId(null) }}
          disabled={disabled}
        >
          <Plus className="h-3.5 w-3.5" />
          Adicionar
        </button>
      </div>

      {isAdding && (
        <ProductForm disabled={disabled} submitLabel="Adicionar" onCancel={() => setIsAdding(false)} onSubmit={handleAdd} />
      )}

      <div className="space-y-2">
        {products.length === 0 ? (
          <p className="rounded-lg border border-panel-border bg-panel-surface px-5 py-6 text-sm text-txt-muted">
            Nenhum produto cadastrado.
          </p>
        ) : (
          products.map((product) =>
            editingId === product.id ? (
              <ProductForm
                key={`${product.id}-edit`}
                disabled={disabled}
                initialValue={product}
                submitLabel="Salvar"
                onCancel={() => setEditingId(null)}
                onSubmit={(p) => handleEdit(product.id, p)}
              />
            ) : (
              <div
                className="flex items-center justify-between rounded-lg border border-panel-border bg-panel-surface px-4 py-3.5 transition-colors hover:border-panel-hover"
                key={product.id}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-1.5">
                    {product.keywords.map((kw) => (
                      <span
                        key={kw}
                        className="inline-flex items-center rounded bg-haumea-600/10 px-2 py-0.5 text-xs font-mono text-haumea-300"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1.5 text-2xs text-txt-muted font-mono">
                    até {formatPrice(product.max_price)}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 ml-4">
                  <button
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-txt-muted transition hover:bg-panel-hover hover:text-txt-primary disabled:opacity-40"
                    type="button"
                    onClick={() => { setEditingId(product.id); setIsAdding(false) }}
                    disabled={disabled}
                    title="Editar"
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-txt-muted transition hover:bg-panel-hover hover:text-danger disabled:opacity-40"
                    type="button"
                    onClick={() => setPendingDelete(product)}
                    disabled={disabled}
                    title="Excluir"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ),
          )
        )}
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Excluir produto"
          message={`Deseja excluir o produto com as palavras-chave "${pendingDelete.keywords.join(', ')}"?`}
          disabled={disabled}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => { onDelete(pendingDelete.id); setPendingDelete(null) }}
        />
      )}
    </section>
  )
}

export default ProductsPanel
