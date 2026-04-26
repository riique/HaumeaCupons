import { useCallback, useEffect, useState } from 'react'

import ChatGroupsPanel from './components/ChatGroupsPanel'
import FindingsTable from './components/FindingsTable'
import LogsPanel from './components/LogsPanel'
import Overview from './components/Overview'
import ProductsPanel from './components/ProductsPanel'
import Sidebar from './components/Sidebar'
import { jsonRequest, requestJson } from './api'
import type { ApiState, FindingsPage, Product, ProductPayload, Tab } from './types'

const emptyState: ApiState = {
  products: [],
  chat_groups: 'all',
  findings: [],
}

function groupsToText(chatGroups: ApiState['chat_groups']) {
  return Array.isArray(chatGroups) ? chatGroups.join('\n') : chatGroups
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-32">
      <span
        className="h-8 w-8 animate-spin rounded-full border-2 border-panel-border border-t-haumea-500"
        aria-hidden="true"
      />
      <p className="text-sm text-txt-muted">Carregando dados...</p>
      <p className="text-2xs text-txt-muted">Verifique se o backend está rodando na porta 8000</p>
    </div>
  )
}

function App() {
  const [state, setState] = useState<ApiState>(emptyState)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')

  const loadState = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true)
    try {
      const next = await requestJson<ApiState>('/api/state')
      setState(next)
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
      setState((c) => ({ ...c, findings: page.findings }))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao atualizar alertas.')
    }
  }, [])

  const mutate = useCallback(
    async (op: () => Promise<unknown>) => {
      setIsMutating(true)
      try {
        await op()
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
    const id = window.setInterval(() => void refreshFindings(), 30_000)
    return () => window.clearInterval(id)
  }, [refreshFindings])

  const addProduct = (p: ProductPayload) =>
    mutate(() => requestJson<Product>('/api/products', jsonRequest('POST', p)))
  const editProduct = (id: number, p: ProductPayload) =>
    mutate(() => requestJson<Product>(`/api/products/${id}`, jsonRequest('PUT', p)))
  const deleteProduct = (id: number) =>
    mutate(() => requestJson<void>(`/api/products/${id}`, { method: 'DELETE' }))
  const saveChatGroups = (g: string) =>
    mutate(() => requestJson('/api/chat-groups', jsonRequest('PUT', { chat_groups: g })))
  const deleteFinding = (id: number) =>
    mutate(() => requestJson<void>(`/api/findings/${id}`, { method: 'DELETE' }))
  const clearFindings = () =>
    mutate(() => requestJson<void>('/api/findings', { method: 'DELETE' }))

  const groupCount = state.chat_groups === 'all'
    ? ('all' as const)
    : Array.isArray(state.chat_groups)
      ? state.chat_groups.length
      : 1

  const content = (() => {
    if (isLoading) return <LoadingState />

    switch (tab) {
      case 'overview':
        return <Overview state={state} />
      case 'products':
        return (
          <ProductsPanel
            products={state.products}
            disabled={isMutating}
            onAdd={addProduct}
            onDelete={deleteProduct}
            onEdit={editProduct}
          />
        )
      case 'groups':
        return (
          <ChatGroupsPanel
            chatGroups={groupsToText(state.chat_groups)}
            disabled={isMutating}
            onSave={saveChatGroups}
          />
        )
      case 'findings':
        return (
          <FindingsTable
            findings={state.findings.slice(0, 200)}
            onDelete={deleteFinding}
            onClearAll={clearFindings}
          />
        )
      case 'logs':
        return <LogsPanel />
      default:
        return null
    }
  })()

  return (
    <div className="min-h-screen bg-panel-bg font-body text-txt-primary antialiased">
      <Sidebar
        active={tab}
        onChange={setTab}
        counts={{
          products: state.products.length,
          groups: groupCount,
          findings: state.findings.length,
        }}
      />

      <main className="min-h-screen p-6 pt-16 lg:ml-56 lg:p-8 lg:pt-8">
        {error && (
          <div className="mb-6 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger" role="alert">
            {error}
          </div>
        )}
        {content}
      </main>
    </div>
  )
}

export default App
