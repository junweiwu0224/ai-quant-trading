import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, formatApiError, parseAiSseData } from './api/client'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('API client hardening', () => {
  it('formats nested validation details without object coercion', () => {
    const message = formatApiError({ detail: [{ loc: ['body', 'ttl_days'], msg: 'must be less than or equal to 30' }] }, 422)

    expect(message).toBe('ttl_days：must be less than or equal to 30')
    expect(message).not.toContain('[object Object]')
  })

  it('carries the selected market on research requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.stockKline('600519', 'daily', 120, 'US')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/stock/kline/600519?period=daily&count=120&market=US',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('exposes the share-link revoke endpoint as a destructive API action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"revoked":true}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.revokeShareLink('link/with spaces')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/decisions/share-links/link%2Fwith%20spaces',
      expect.objectContaining({ credentials: 'include', method: 'DELETE' }),
    )
  })

  it('parses AI Runtime SSE terminal events and malformed frames safely', () => {
    expect(parseAiSseData('{"type":"done","result":{"ok":true}}')).toEqual({ type: 'done', result: { ok: true } })
    expect(parseAiSseData('[DONE]')).toEqual({ type: 'done' })
    expect(parseAiSseData('not-json')).toMatchObject({ type: 'error', error: 'invalid_sse_json' })
  })

  it('rejects a non-terminal decision command when polling times out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"id":"cmd-1","status":"running"}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.waitDecisionCommand('cmd-1', 0)).rejects.toMatchObject({
      status: 408,
      message: '决策命令等待超时（当前状态：running）',
    })
  })

  it('uses the unified AI Runtime status endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"runtime":"ready"}', {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.aiStatus()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ai/status',
      expect.objectContaining({ credentials: 'include' }),
    )
  })
})
