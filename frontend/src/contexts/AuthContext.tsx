import { onAuthStateChanged, signOut, type User } from 'firebase/auth'
import { doc, getDoc } from 'firebase/firestore'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { auth, db, firebaseConfigReady } from '../firebase'

type AuthContextValue = {
  user: User | null
  loading: boolean
  ready: boolean
  isAdmin: boolean
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    const firebaseAuth = auth
    if (!firebaseAuth) {
      setLoading(false)
      return undefined
    }

    const unsubscribe = onAuthStateChanged(firebaseAuth, (nextUser) => {
      setUser(nextUser)
      setIsAdmin(false)
      if (!nextUser || !db) {
        setLoading(false)
        return
      }

      void getDoc(doc(db, 'admins', nextUser.uid))
        .then((snap) => setIsAdmin(snap.exists()))
        .catch(() => setIsAdmin(false))
        .finally(() => setLoading(false))
    })
    return unsubscribe
  }, [])

  const logout = useCallback(async () => {
    if (auth) await signOut(auth)
  }, [])

  const value = useMemo(
    () => ({ user, loading, ready: firebaseConfigReady, isAdmin, logout }),
    [user, loading, isAdmin, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth deve ser usado dentro de AuthProvider')
  return value
}
