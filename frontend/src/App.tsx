import { LogOut } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useNavigate,
  useOutletContext,
} from 'react-router-dom'

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
import type { ApiState, ProductPayload } from './types'

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

type DashboardContext = {
  state: ApiState
  isLoading: boolean
  isMutating: boolean
  addProduct: (product: ProductPayload) => void
  editProduct: (id: number | string, product: ProductPayload) => void
  deleteProduct: (id: number | string) => void
  deleteFinding: (id: number | string) => void
  clearFindings: () => void
}

type DashboardLayoutProps = DashboardContext & {
  error: string
}

function useDashboardContext() {
  return useOutletContext<DashboardContext>()
}

function LoginRoute() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (user) return <Navigate to="/geral" replace />

  return <Login onRegister={() => navigate('/register')} />
}

function RegisterRoute() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (user) return <Navigate to="/geral" replace />

  return <Register onLogin={() => navigate('/login')} />
}

function DashboardLayout({
  state,
  isLoading,
  isMutating,
  error,
  addProduct,
  editProduct,
  deleteProduct,
  deleteFinding,
  clearFindings,
}: DashboardLayoutProps) {
  const { user, logout } = useAuth()

  if (!user) return <Navigate to="/login" replace />

  const context: DashboardContext = {
    state,
    isLoading,
    isMutating,
    addProduct,
    editProduct,
    deleteProduct,
    deleteFinding,
    clearFindings,
  }

  return (
    <div className="min-h-screen bg-panel-bg font-body text-txt-primary antialiased">
      <Sidebar
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
        <Outlet context={context} />
      </main>
    </div>
  )
}

function OverviewRoute() {
  const { state, isLoading } = useDashboardContext()

  if (isLoading) return <LoadingState />

  return <Overview state={state} />
}

function ProductsRoute() {
  const { state, isLoading, isMutating, addProduct, editProduct, deleteProduct } = useDashboardContext()

  if (isLoading) return <LoadingState />

  return (
    <ProductsPanel
      products={state.products}
      disabled={isMutating}
      onAdd={addProduct}
      onDelete={deleteProduct}
      onEdit={editProduct}
    />
  )
}

function FindingsRoute() {
  const { state, isLoading, deleteFinding, clearFindings } = useDashboardContext()

  if (isLoading) return <LoadingState />

  return (
    <FindingsTable
      findings={state.findings.slice(0, 200)}
      onDelete={deleteFinding}
      onClearAll={clearFindings}
    />
  )
}

function App() {
  const { user, loading: authLoading, ready: authReady } = useAuth()
  const [state, setState] = useState<ApiState>(emptyState)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')

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

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/register" element={<RegisterRoute />} />
        <Route
          element={(
            <DashboardLayout
              state={state}
              isLoading={isLoading}
              isMutating={isMutating}
              error={error}
              addProduct={addProduct}
              editProduct={editProduct}
              deleteProduct={deleteProduct}
              deleteFinding={deleteFinding}
              clearFindings={clearFindings}
            />
          )}
        >
          <Route index element={<OverviewRoute />} />
          <Route path="geral" element={<OverviewRoute />} />
          <Route path="produtos" element={<ProductsRoute />} />
          <Route path="alertas" element={<FindingsRoute />} />
        </Route>
        <Route path="*" element={<Navigate to="/geral" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
