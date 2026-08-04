import { beforeEach, describe, expect, it, vi } from 'vitest'

import { hasSession, setSession } from '@/api/client'
import { auth } from '@/auth/state'

describe('auth state', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('revokes the server session and always clears local tokens', async () => {
    setSession({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 60,
    })
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await auth.logout()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/auth/logout')
    expect(hasSession()).toBe(false)
  })
})
