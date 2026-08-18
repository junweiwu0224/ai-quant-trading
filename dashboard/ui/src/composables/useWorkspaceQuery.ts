import { computed, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'
import { useResearchContextStore, type WorkspaceQueryState } from '../stores/researchContext'

function first(value: unknown): string {
  if (Array.isArray(value)) return String(value[0] || '')
  return value == null ? '' : String(value)
}

function parseFilters(value: string): Record<string, string | number | boolean> {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>
    return Object.fromEntries(Object.entries(parsed).filter(([, item]) => ['string', 'number', 'boolean'].includes(typeof item))) as Record<string, string | number | boolean>
  } catch {
    return {}
  }
}

function queryState(query: LocationQuery): Partial<WorkspaceQueryState> {
  const page = Number(first(query.page))
  return {
    tab: first(query.tab) || null,
    sort: first(query.sort) || null,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    selected: first(query.selected).split(',').map((item) => item.trim()).filter(Boolean),
    timeframe: first(query.timeframe) || null,
    filters: parseFilters(first(query.filters)),
  }
}

function serializeState(state: WorkspaceQueryState): LocationQueryRaw {
  const next: LocationQueryRaw = {}
  if (state.tab) next.tab = state.tab
  if (state.sort) next.sort = state.sort
  if (state.page > 1) next.page = String(state.page)
  if (state.selected.length) next.selected = state.selected.join(',')
  if (state.timeframe) next.timeframe = state.timeframe
  if (Object.keys(state.filters).length) next.filters = JSON.stringify(state.filters)
  return next
}

export function useWorkspaceQuery() {
  const route = useRoute()
  const router = useRouter()
  const context = useResearchContextStore()
  const state = computed(() => context.context.query)

  function hydrate() {
    context.setQuery(queryState(route.query))
  }

  function update(next: Partial<WorkspaceQueryState>) {
    context.setQuery(next)
    const query = { ...route.query, ...serializeState(context.context.query) }
    for (const key of ['tab', 'sort', 'page', 'selected', 'timeframe', 'filters']) {
      if (!(key in serializeState(context.context.query))) delete query[key]
    }
    void router.replace({ query })
  }

  watch(() => route.query, hydrate, { immediate: true, deep: true })

  return { state, hydrate, update }
}
