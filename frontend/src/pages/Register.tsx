import { createUserWithEmailAndPassword, updateProfile } from 'firebase/auth'
import { doc, serverTimestamp, setDoc } from 'firebase/firestore'
import { UserPlus } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { auth, db } from '../firebase'

type RegisterProps = {
  onLogin: () => void
}

const inputCls =
  'w-full rounded-md border border-panel-border bg-panel-bg px-3 py-2.5 text-sm text-txt-primary outline-none transition placeholder:text-txt-muted focus:border-haumea-600'

function Register({ onLogin }: RegisterProps) {
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!auth || !db) {
      setError('Firebase não está configurado no frontend.')
      return
    }
    if (password !== confirmPassword) {
      setError('As senhas não conferem.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const credential = await createUserWithEmailAndPassword(auth, email.trim(), password)
      await updateProfile(credential.user, { displayName: displayName.trim() })
      await setDoc(doc(db, 'users', credential.user.uid), {
        email: credential.user.email,
        displayName: displayName.trim(),
        createdAt: serverTimestamp(),
        lastLoginAt: serverTimestamp(),
      })
      window.history.pushState({}, '', '/')
      window.dispatchEvent(new PopStateEvent('popstate'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao criar conta.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-panel-bg px-4 py-10 text-txt-primary">
      <section className="w-full max-w-md rounded-lg border border-panel-border bg-panel-surface p-6">
        <div className="mb-6">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-haumea-600">
            <span className="text-base font-bold text-white">H</span>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Criar conta</h1>
          <p className="mt-1 text-sm text-txt-muted">Cadastre seu acesso ao dashboard.</p>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-1.5">
            <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Nome</span>
            <input className={inputCls} value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
          </label>
          <label className="block space-y-1.5">
            <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Email</span>
            <input className={inputCls} type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1.5">
              <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Senha</span>
              <input className={inputCls} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            <label className="block space-y-1.5">
              <span className="text-2xs font-medium uppercase tracking-wide text-txt-muted">Confirmar</span>
              <input className={inputCls} type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
            </label>
          </div>
          <button
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-haumea-600 px-4 text-sm font-medium text-white transition hover:bg-haumea-500 disabled:opacity-50"
            type="submit"
            disabled={submitting}
          >
            <UserPlus className="h-4 w-4" />
            Criar conta
          </button>
        </form>

        <button className="mt-5 text-sm text-haumea-400 transition hover:text-haumea-300" type="button" onClick={onLogin}>
          Já tenho conta
        </button>
      </section>
    </main>
  )
}

export default Register
