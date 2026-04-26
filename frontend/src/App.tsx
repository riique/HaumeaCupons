import { useCallback, useEffect, useState } from 'react'

import ChatGroupsPanel from './components/ChatGroupsPanel'
import FindingsTable from './components/FindingsTable'
import Footer from './components/Footer'
import Header from './components/Header'
import ProductsPanel from './components/ProductsPanel'
import type { ApiState, FindingsPage, Product, ProductPayload } from './types'

const emptyState: ApiState = {
  products: [],
  chat_groups: 'all',
  findings: [],
}

function groupsToText(chatGroups: ApiState['chat_groups']) {
  return Array.isArray(chatGroups) ? chatGroups.join('\n') : chatGroups
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = 'A API retornou erro.'
    try {
      const payload = (await response.json()) as { detail?: string | { msg?: string }[] }
      if (typeof payload.detail === 'string') {
        message = payload.detail
      } else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
        message = payload.detail[0].msg
      }
    } catch {
      message = response.statusText || message
    }
    throw new Error(message)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-sm font-light text-slate-500">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-action" aria-hidden="true" />
      Carregando dados...
    </div>
  )
}

function App() {
  const [state, setState] = useState<ApiState>(emptyState)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')

  const loadState = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      const nextState = await requestJson<ApiState>('/api/state')
      setState(nextState)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao carregar dados.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const refreshFindings = useCallback(async () => {
    try {
      const page = await requestJson<FindingsPage>('/api/findings?limit=200')
      setState((current) => ({ ...current, findings: page.findings }))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao atualizar alertas.')
    }
  }, [])

  const mutate = useCallback(
    async (operation: () => Promise<unknown>) => {
      setIsMutating(true)
      try {
        await operation()
        await loadState()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Falha ao salvar alteração.')
      } finally {
        setIsMutating(false)
      }
    },
    [loadState],
  )

  useEffect(() => {
    void loadState(true)
  }, [loadState])

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refreshFindings()
    }, 30_000)
    return () => window.clearInterval(interval)
  }, [refreshFindings])

  const addProduct = (product: ProductPayload) =>
    mutate(() => requestJson<Product>('/api/products', jsonRequest('POST', product)))
  const editProduct = (id: number, product: ProductPayload) =>
    mutate(() => requestJson<Product>(`/api/products/${id}`, jsonRequest('PUT', product)))
  const deleteProduct = (id: number) => mutate(() => requestJson<void>(`/api/products/${id}`, { method: 'DELETE' }))
  const saveChatGroups = (chatGroups: string) =>
    mutate(() => requestJson('/api/chat-groups', jsonRequest('PUT', { chat_groups: chatGroups })))

  return (
    <div className="min-h-screen bg-white font-sans text-ink antialiased">
      <Header />
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-6 py-8 sm:px-8 lg:px-10">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : null}
        {isLoading ? (
          <LoadingState />
        ) : (
          <>
            <ProductsPanel
              products={state.products}
              disabled={isMutating}
              onAdd={addProduct}
              onDelete={deleteProduct}
              onEdit={editProduct}
            />
            <ChatGroupsPanel
              chatGroups={groupsToText(state.chat_groups)}
              disabled={isMutating}
              onSave={saveChatGroups}
            />
            <FindingsTable findings={state.findings.slice(0, 200)} />
          </>
        )}
      </main>
      <Footer />
    </div>
  )
}

export default App
