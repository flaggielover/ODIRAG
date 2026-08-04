import { computed, reactive } from 'vue'

import { apiRequest, clearSession, hasSession, setSession } from '@/api/client'
import type { TokenPair, User } from '@/api/types'

const state = reactive({
  user: null as User | null,
  ready: false,
  pending: false,
})

let bootstrapPromise: Promise<void> | null = null

export const auth = {
  state,
  authenticated: computed(() => state.user !== null),
  async bootstrap(): Promise<void> {
    if (state.ready) return
    if (!bootstrapPromise) {
      bootstrapPromise = (async () => {
        if (hasSession()) {
          try {
            state.user = await apiRequest<User>('/auth/me')
          } catch {
            clearSession()
          }
        }
        state.ready = true
      })().finally(() => {
        bootstrapPromise = null
      })
    }
    await bootstrapPromise
  },
  async login(username: string, password: string): Promise<void> {
    state.pending = true
    try {
      const tokens = await apiRequest<TokenPair>(
        '/auth/login',
        { method: 'POST', body: JSON.stringify({ username, password }) },
        { auth: false },
      )
      setSession(tokens)
      state.user = await apiRequest<User>('/auth/me')
      state.ready = true
    } finally {
      state.pending = false
    }
  },
  async logout(): Promise<void> {
    try {
      if (hasSession()) {
        await apiRequest<void>('/auth/logout', { method: 'POST' })
      }
    } catch {
      // Local logout must still complete when the API or network is unavailable.
    } finally {
      clearSession()
      state.user = null
      state.ready = true
    }
  },
}

window.addEventListener('odirag:auth-expired', () => {
  state.user = null
  state.ready = true
})
