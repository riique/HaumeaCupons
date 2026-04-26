import { Check, Edit3, Plus, Trash2, X } from 'lucide-react'
import { type FormEvent, useState } from 'react'

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

const emptyProduct: ProductPayload = {
  keyword: '',
  min_price: 0,
  max_price: 0,
}

function formatPrice(value: number) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 2,
  }).format(value)
}

function ProductForm({ disabled, initialValue = emptyProduct, submitLabel, onCancel, onSubmit }: ProductFormProps) {
  const [keyword, setKeyword] = useState(initialValue.keyword)
  const [minPrice, setMinPrice] = useState(String(initialValue.min_price))
  const [maxPrice, setMaxPrice] = useState(String(initialValue.max_price))
  const [error, setError] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const min = Number(minPrice)
    const max = Number(maxPrice)
    if (!keyword.trim()) {
      setError('Informe a palavra-chave.')
      return
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      setError('Informe preços válidos.')
      return
    }
    if (min < 0 || max < 0) {
      setError('Os preços não podem ser negativos.')
      return
    }
    if (max < min) {
      setError('O preço máximo deve ser maior ou igual ao mínimo.')
      return
    }
    setError('')
    onSubmit({
      keyword: keyword.trim(),
      min_price: min,
      max_price: max,
    })
  }

  return (
    <form className="grid gap-4 rounded-lg border border-gray-100 p-5 sm:grid-cols-[1fr_140px_140px_auto]" onSubmit={handleSubmit}>
      <label className="space-y-2">
        <span className="text-xs font-light text-slate-400">Palavra-chave</span>
        <input
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-light text-ink outline-none transition focus:border-action"
          name="keyword"
          required
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          disabled={disabled}
        />
      </label>
      <label className="space-y-2">
        <span className="text-xs font-light text-slate-400">Preço mínimo</span>
        <input
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-light text-ink outline-none transition focus:border-action"
          name="min_price"
          required
          min="0"
          step="0.01"
          type="number"
          value={minPrice}
          onChange={(event) => setMinPrice(event.target.value)}
          disabled={disabled}
        />
      </label>
      <label className="space-y-2">
        <span className="text-xs font-light text-slate-400">Preço máximo</span>
        <input
          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-light text-ink outline-none transition focus:border-action"
          name="max_price"
          required
          min="0"
          step="0.01"
          type="number"
          value={maxPrice}
          onChange={(event) => setMaxPrice(event.target.value)}
          disabled={disabled}
        />
      </label>
      <div className="flex items-end gap-2">
        <button
          className="inline-flex h-11 items-center gap-2 rounded-lg border border-action px-4 text-sm font-light text-action transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
          type="submit"
          disabled={disabled}
        >
          <Check className="h-4 w-4" aria-hidden="true" />
          {submitLabel}
        </button>
        {onCancel ? (
          <button
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-gray-200 text-slate-400 transition hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            onClick={onCancel}
            disabled={disabled}
            aria-label="Cancelar"
            title="Cancelar"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {error ? <p className="text-sm text-red-600 sm:col-span-4">{error}</p> : null}
    </form>
  )
}

function ProductsPanel({ products, disabled, onAdd, onDelete, onEdit }: ProductsPanelProps) {
  const [isAdding, setIsAdding] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Product | null>(null)

  const handleAdd = (product: ProductPayload) => {
    onAdd(product)
    setIsAdding(false)
  }

  const handleEdit = (id: number, product: ProductPayload) => {
    onEdit(id, product)
    setEditingId(null)
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-light text-ink">Produtos</h2>
          <p className="mt-1 text-sm font-light text-slate-400">Produtos monitorados pelo bot.</p>
        </div>
        <button
          className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-gray-200 px-4 text-sm font-light text-action transition hover:border-action disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          onClick={() => {
            setIsAdding((current) => !current)
            setEditingId(null)
          }}
          disabled={disabled}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Adicionar
        </button>
      </div>

      {isAdding ? (
        <ProductForm disabled={disabled} submitLabel="Adicionar" onCancel={() => setIsAdding(false)} onSubmit={handleAdd} />
      ) : null}

      <div className="space-y-3">
        {products.length === 0 ? (
          <p className="rounded-lg border border-gray-100 px-5 py-6 text-sm font-light text-slate-400">
            Nenhum produto cadastrado
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
                onSubmit={(nextProduct) => handleEdit(product.id, nextProduct)}
              />
            ) : (
              <div
                className="flex flex-col gap-4 rounded-lg border border-gray-100 px-5 py-5 shadow-sm sm:flex-row sm:items-center sm:justify-between"
                key={product.id}
              >
                <div className="min-w-0">
                  <p className="truncate text-base font-light text-ink">{product.keyword}</p>
                  <p className="mt-1 text-sm font-light text-slate-400">
                    {formatPrice(product.min_price)} → {formatPrice(product.max_price)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-100 text-slate-400 transition hover:border-gray-200 hover:text-action disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={() => {
                      setEditingId(product.id)
                      setIsAdding(false)
                    }}
                    disabled={disabled}
                    aria-label={`Editar ${product.keyword}`}
                    title="Editar"
                  >
                    <Edit3 className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-100 text-slate-400 transition hover:border-gray-200 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                    type="button"
                    onClick={() => setPendingDelete(product)}
                    disabled={disabled}
                    aria-label={`Excluir ${product.keyword}`}
                    title="Excluir"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            ),
          )
        )}
      </div>
      {pendingDelete ? (
        <ConfirmDialog
          title="Excluir produto"
          message={`Deseja excluir "${pendingDelete.keyword}"?`}
          disabled={disabled}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            onDelete(pendingDelete.id)
            setPendingDelete(null)
          }}
        />
      ) : null}
    </section>
  )
}

export default ProductsPanel
