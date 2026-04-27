import { signInWithEmailAndPassword } from 'firebase/auth'
import { doc, serverTimestamp, setDoc } from 'firebase/firestore'
import { LogIn } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { auth, db } from '../firebase'

type LoginProps = {
  onRegister: () => void
}

const inputCls =
  'w-full rounded-md border border-panel-border bg-panel-bg px-3 py-2.5 text-sm text-txt-primary outline-none transition placeholder:text-txt-muted focus:border-haumea-600'

function Login({ onRegister }: LoginProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!auth) {
      setError('Firebase não está configurado no frontend.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const credential = await signInWithEmailAndPassword(auth, email.trim(), password)
      if (db) {
        await setDoc(
          doc(db, 'users', credential.user.uid),
          {
            email: credential.user.email,
            displayName: credential.user.displayName || '',
            lastLoginAt: serverTimestamp(),
          },
          { merge: true },
        )
      }
      window.history.pushState({}, '', '/')
      window.dispatchEvent(new PopStateEvent('popstate'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao entrar.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-panel-bg px-4 py-10 text-txt-primary">
      <section className="w-full max-w-sm rounded-lg border border-panel-border bg-panel-surface p-6">
        <div className="mb-6">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-haumea-600">
            <span className="text-base font-bold text-white">H</span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Entrar</h1>
          <p className="mt-1 text-sm text-txt-muted">Acesse o painel HaumeaCupons.</p>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-1.5">
            <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Email</span>
            <input className={inputCls} type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="block space-y-1.5">
            <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Senha</span>
            <input className={inputCls} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          <button
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-haumea-600 px-4 text-sm font-medium text-white transition hover:bg-haumea-500 disabled:opacity-50"
            type="submit"
            disabled={submitting}
          >
            <LogIn className="h-4 w-4" />
            Entrar
          </button>
        </form>

        <button className="mt-5 text-sm text-haumea-400 transition hover:text-haumea-300" type="button" onClick={onRegister}>
          Criar conta
        </button>
      </section>
    </main>
  )
}

export default Login
