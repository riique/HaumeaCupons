import { LogOut } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import FindingsTable from './components/FindingsTable'
import Overview from './components/Overview'
import ProductsPanel from './components/ProductsPanel'
import Sidebar from './components/Sidebar'
import {
  addProduct as addProductToFirestore,
  clearAllFindings,
  deleteFinding as deleteFindingFromFirestore,
  deleteProduct as deleteProductFromFirestore,
  fetchDashboardState,
  fetchFindings,
  updateProduct as updateProductInFirestore,
} from './api'
import { useAuth } from './contexts/AuthContext'
import Login from './pages/Login'
import Register from './pages/Register'
import type { ApiState, ProductPayload, Tab } from './types'

const emptyState: ApiState = {
  products: [],
  findings: [],
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-32">
      <span
        className="h-8 w-8 animate-spin rounded-full border-2 border-panel-border border-t-haumea-500"
        aria-hidden="true"
      />
      <p className="text-sm text-txt-muted">Carregando dados...</p>
    </div>
  )
}

function App() {
  const { user, loading: authLoading, ready: authReady, logout } = useAuth()
  const [state, setState] = useState<ApiState>(emptyState)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [path, setPath] = useState(window.location.pathname)

  const navigate = useCallback((nextPath: string) => {
    window.history.pushState({}, '', nextPath)
    setPath(nextPath)
  }, [])

  useEffect(() => {
    const updatePath = () => setPath(window.location.pathname)
    window.addEventListener('popstate', updatePath)
    return () => window.removeEventListener('popstate', updatePath)
  }, [])

  const loadState = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true)
    try {
      const next = await fetchDashboardState()
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
      const findings = await fetchFindings(200)
      setState((c) => ({ ...c, findings }))
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
    if (!user) return
    void loadState(true)
  }, [loadState, user])

  useEffect(() => {
    if (!user) return undefined
    const id = window.setInterval(() => void refreshFindings(), 30_000)
    return () => window.clearInterval(id)
  }, [refreshFindings, user])

  useEffect(() => {
    if (user && (path === '/login' || path === '/register')) {
      navigate('/')
    }
  }, [navigate, path, user])

  const addProduct = (p: ProductPayload) =>
    mutate(() => addProductToFirestore(p))
  const editProduct = (id: number | string, p: ProductPayload) =>
    mutate(() => updateProductInFirestore(id, p))
  const deleteProduct = (id: number | string) =>
    mutate(() => deleteProductFromFirestore(id))
  const deleteFinding = (id: number | string) =>
    mutate(() => deleteFindingFromFirestore(id))
  const clearFindings = () =>
    mutate(() => clearAllFindings())

  if (authLoading) {
    return (
      <div className="min-h-screen bg-panel-bg font-body text-txt-primary antialiased">
        <LoadingState />
      </div>
    )
  }

  if (!authReady) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-panel-bg px-4 text-txt-primary">
        <section className="w-full max-w-md rounded-lg border border-panel-border bg-panel-surface p-6">
          <h1 className="text-lg font-semibold tracking-tight">Firebase não configurado</h1>
          <p className="mt-2 text-sm text-txt-muted">
            Defina as variáveis Vite `VITE_FIREBASE_*` antes de compilar o frontend.
          </p>
        </section>
      </main>
    )
  }

  if (!user) {
    return path === '/register'
      ? <Register onLogin={() => navigate('/login')} />
      : <Login onRegister={() => navigate('/register')} />
  }

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
      case 'findings':
        return (
          <FindingsTable
            findings={state.findings.slice(0, 200)}
            onDelete={deleteFinding}
            onClearAll={clearFindings}
          />
        )
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
          findings: state.findings.length,
        }}
      />

      <main className="min-h-screen p-6 pt-16 lg:ml-56 lg:p-8 lg:pt-8">
        <header className="mb-6 flex items-center justify-end gap-3">
          <div className="min-w-0 text-right">
            <p className="truncate text-sm font-medium text-txt-primary">{user.displayName || user.email}</p>
            <p className="truncate text-2xs text-txt-muted">{user.email}</p>
          </div>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-panel-border text-txt-muted transition hover:border-danger/50 hover:text-danger"
            type="button"
            onClick={() => void logout()}
            title="Sair"
            aria-label="Sair"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </header>
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
