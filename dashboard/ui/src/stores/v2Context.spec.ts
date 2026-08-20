import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../api/client'
import { useV2ContextStore } from './v2Context'

const context = (overrides: Record<string, unknown> = {}) => ({
  schema_version: 'v2-context-1',
  workspace_id: 'workspace-a',
  account_id: 'paper-a',
  environment: 'paper',
  live_enabled: false,
  execution_run: { id: 'run-a', status: 'running', readiness: 'ready' },
  runtime: { status: 'running' },
  tasks: [],
  reconciliations: [],
  ...overrides,
})

describe('V2 context store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('blocks controls before durable context loads', () => {
    expect(useV2ContextStore().controlsBlocked).toBe(true)
  })

  it('fails closed for live or malformed context', async () => {
    vi.spyOn(api, 'paperContext').mockResolvedValue({ environment: 'live', live_enabled: true })
    const store = useV2ContextStore()

    await store.load('paper-a', 'workspace-a')

    expect(store.error).toContain('paper fail-closed')
    expect(store.controlsBlocked).toBe(true)
  })

  it('keeps an unbound Paper account blocked', async () => {
    vi.spyOn(api, 'paperContext').mockResolvedValue(context({ account_id: '', execution_run: { id: null, status: 'unknown', readiness: 'unbound' } }))
    const store = useV2ContextStore()

    await store.load('', 'workspace-a')

    expect(store.loaded).toBe(true)
    expect(store.readiness).toBe('unbound')
    expect(store.controlsBlocked).toBe(true)
  })

  it('allows controls only for a ready Paper context', async () => {
    vi.spyOn(api, 'paperContext').mockResolvedValue(context())
    const store = useV2ContextStore()

    await store.load('paper-a', 'workspace-a')

    expect(store.status).toBe('running')
    expect(store.readiness).toBe('ready')
    expect(store.controlsBlocked).toBe(false)
  })
})
