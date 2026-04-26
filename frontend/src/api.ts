const DASHBOARD_KEY_STORAGE = 'haumea.dashboardKey'

function dashboardKey() {
  return window.localStorage.getItem(DASHBOARD_KEY_STORAGE)?.trim() || ''
}

function promptDashboardKey() {
  const key = window.prompt('Chave de acesso do dashboard')
  if (!key?.trim()) return false
  window.localStorage.setItem(DASHBOARD_KEY_STORAGE, key.trim())
  return true
}

function withAuthHeaders(headers?: HeadersInit) {
  const next = new Headers(headers)
  const key = dashboardKey()
  if (key) next.set('Authorization', `Bearer ${key}`)
  return next
}

export async function fetchWithDashboardAuth(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, { ...init, headers: withAuthHeaders(init?.headers) })
  if (response.status !== 401) return response

  window.localStorage.removeItem(DASHBOARD_KEY_STORAGE)
  if (!promptDashboardKey()) return response
  return fetch(path, { ...init, headers: withAuthHeaders(init?.headers) })
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithDashboardAuth(path, init)
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

export function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}
