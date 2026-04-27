import { onAuthStateChanged, signOut, type User } from 'firebase/auth'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { auth, firebaseConfigReady } from '../firebase'

type AuthContextValue = {
  user: User | null
  loading: boolean
  ready: boolean
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const firebaseAuth = auth
    if (!firebaseAuth) {
      setLoading(false)
      return undefined
    }

    const unsubscribe = onAuthStateChanged(firebaseAuth, (nextUser) => {
      setUser(nextUser)
      setLoading(false)
    })
    return unsubscribe
  }, [])

  const logout = useCallback(async () => {
    if (auth) await signOut(auth)
  }, [])

  const value = useMemo(
    () => ({ user, loading, ready: firebaseConfigReady, logout }),
    [user, loading, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth deve ser usado dentro de AuthProvider')
  return value
}
