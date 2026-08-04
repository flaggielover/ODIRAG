import type { ApiErrorPayload, TokenPair } from '@/api/types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')
const SESSION_KEY = 'odirag.session'

interface StoredSession {
  accessToken: string
  refreshToken: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(
    message: string,
    options: { status: number; code?: string; details?: unknown; requestId?: string | null },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code ?? 'HTTP_ERROR'
    this.details = options.details
    this.requestId = options.requestId ?? null
  }
}

let session = readSession()
let refreshPromise: Promise<boolean> | null = null

export function hasSession(): boolean {
  return Boolean(session?.accessToken && session.refreshToken)
}

export function setSession(tokens: TokenPair): void {
  session = {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  session = null
  sessionStorage.removeItem(SESSION_KEY)
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; retry?: boolean } = {},
): Promise<T> {
  const auth = options.auth ?? true
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  headers.set('Accept', 'application/json')
  if (auth && session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (response.status === 401 && auth && options.retry !== false && (await refreshSession())) {
    return apiRequest<T>(path, init, { auth, retry: false })
  }
  if (!response.ok) {
    throw await responseError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function refreshSession(): Promise<boolean> {
  if (!session?.refreshToken) {
    expireSession()
    return false
  }
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ refresh_token: session?.refreshToken }),
        })
        if (!response.ok) return false
        setSession((await response.json()) as TokenPair)
        return true
      } catch {
        return false
      } finally {
        refreshPromise = null
      }
    })()
  }
  const refreshed = await refreshPromise
  if (!refreshed) expireSession()
  return refreshed
}

async function responseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload = {}
  try {
    payload = (await response.json()) as ApiErrorPayload
  } catch {
    payload = {}
  }
  return new ApiError(payload.error?.message ?? `请求失败（HTTP ${response.status}）`, {
    status: response.status,
    code: payload.error?.code,
    details: payload.error?.details,
    requestId: payload.error?.request_id ?? response.headers.get('x-request-id'),
  })
}

function readSession(): StoredSession | null {
  const value = sessionStorage.getItem(SESSION_KEY)
  if (!value) return null
  try {
    const parsed = JSON.parse(value) as Partial<StoredSession>
    if (typeof parsed.accessToken === 'string' && typeof parsed.refreshToken === 'string') {
      return { accessToken: parsed.accessToken, refreshToken: parsed.refreshToken }
    }
  } catch {
    sessionStorage.removeItem(SESSION_KEY)
  }
  return null
}

function expireSession(): void {
  clearSession()
  window.dispatchEvent(new CustomEvent('odirag:auth-expired'))
}
