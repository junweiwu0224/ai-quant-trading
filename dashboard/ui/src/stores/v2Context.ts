import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'

export type V2Task = {
  id: string
  command_id?: string
  kind?: string
  status?: string
  updated_at?: number
  [key: string]: unknown
}

export type V2Context = {
  schema_version?: string
  workspace_id: string
  account_id: string
  environment: 'paper' | 'live' | string
  live_enabled: boolean
  paper?: Record<string, unknown>
  execution_run?: { id?: string | null; status?: string; readiness?: string }
  runtime?: { status?: string; owner_id?: string | null; updated_at?: number | null }
  tasks?: V2Task[]
  reconciliations?: Array<Record<string, unknown>>
  ai_authority?: string
  source?: string
  [key: string]: unknown
}

export const useV2ContextStore = defineStore('v2Context', () => {
  const context = ref<V2Context | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')

  const status = computed(() => String(context.value?.execution_run?.status || context.value?.paper?.status || 'unknown'))
  const readiness = computed(() => String(context.value?.execution_run?.readiness || 'unknown'))
  const reconciliationRequired = computed(() => Boolean(context.value?.reconciliations?.length || context.value?.paper?.reconciliation_required || readiness.value === 'reconciliation_required'))
  const controlsBlocked = computed(() => !loaded.value || Boolean(error.value) || !context.value?.account_id || reconciliationRequired.value || ['unknown', 'blocked', 'failed', 'halted', 'halt_requested', 'reconciling', 'reconciliation_blocked'].includes(status.value) || ['unknown', 'unbound', 'blocked', 'failed', 'halted', 'halt_requested', 'reconciling', 'reconciliation_blocked'].includes(readiness.value))

  async function load(accountId = 'paper-default', workspaceId = 'default') {
    loading.value = true
    error.value = ''
    try {
      const next = await api.paperContext(accountId, workspaceId) as V2Context
      if (!next || typeof next !== 'object' || next.environment !== 'paper' || next.live_enabled !== false) throw new Error('V2 上下文不满足 paper fail-closed 契约')
      context.value = next
      loaded.value = true
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : 'V2 持久化上下文暂不可用'
    } finally {
      loading.value = false
    }
  }

  function clear() {
    context.value = null
    loaded.value = false
    error.value = ''
  }

  return { context, loading, loaded, error, status, readiness, reconciliationRequired, controlsBlocked, load, clear }
})
