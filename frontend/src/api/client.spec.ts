import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest, clearSession, setSession } from '@/api/client'

describe('api client', () => {
  beforeEach(() => {
    clearSession()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('refreshes an expired access token once and retries the request', async () => {
    setSession({
      access_token: 'expired-access',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      expires_in: 60,
    })
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
            token_type: 'bearer',
            expires_in: 60,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest<{ ok: boolean }>('/protected')).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const retryInit = fetchMock.mock.calls[2]?.[1]
    expect(new Headers(retryInit?.headers).get('Authorization')).toBe('Bearer new-access')
  })

  it('parses the structured backend error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'RESOURCE_CONFLICT',
              message: 'conflict detected',
              request_id: 'request-123',
            },
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    const error = await apiRequest('/conflict', {}, { auth: false }).catch(
      (caught: unknown) => caught,
    )
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: 'RESOURCE_CONFLICT',
      message: 'conflict detected',
      requestId: 'request-123',
    })
  })
})
