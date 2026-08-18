import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import IntelligenceView from './IntelligenceView.vue'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'

vi.mock('../api/client', () => ({
  api: {
    marketBreadth: vi.fn(),
    marketSectors: vi.fn(),
    marketHeatmap: vi.fn(),
    marketHotspot: vi.fn(),
    marketNews: vi.fn(),
    signalTop: vi.fn(),
    marketSnapshot: vi.fn(),
    iwencai: vi.fn(),
  },
}))

const unavailable = { success: false, data_state: 'not_integrated', source: 'market_capability' }
const snapshot = {
  success: true,
  available: true,
  market: 'US',
  provider: 'Yahoo Finance',
  source: 'yahoo_finance',
  coverage_pct: 42,
  data_state: 'manual_research',
  manual_research_only: true,
  index: { index: { name: 'S&P 500', symbol: '^GSPC', price: 5200, change_pct: 1.25 } },
  universe: { total: 20 },
  breadth: { available: true, total_stocks: 20, up_count: 12, down_count: 6, flat_count: 2 },
  sectors: { items: [{ name: 'Technology', change_pct: 1.5, up_count: 8, down_count: 2, leader: 'AAPL' }] },
  heatmap: { items: [{ name: 'Technology', change_pct: 1.5, up_count: 8, down_count: 2 }] },
  hotspots: { items: [{ name: 'AI infrastructure', reason: 'Proxy research context', change_pct: 2.1 }] },
  news: { items: [{ title: 'Provider snapshot news', source: 'Yahoo Finance RSS', published_at: '2026-08-18' }] },
  signals: { items: [{ symbol: 'AAPL', name: 'Apple', score: 0.82, source: 'proxy', validation_status: 'unverified' }] },
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
}

describe('IntelligenceView provider snapshot contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.values(api).forEach((method) => {
      if (typeof method === 'function') vi.mocked(method).mockResolvedValue(unavailable as never)
    })
    vi.mocked(api.marketSnapshot).mockResolvedValue(snapshot)
  })

  it('renders US proxy snapshot data instead of fixed not-integrated copy', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAppStore().setMarket('US')
    const appRouter = router()
    const wrapper = mount(IntelligenceView, { global: { plugins: [pinia, appRouter] } })
    await appRouter.isReady()
    await flushPromises()

    expect(api.marketSnapshot).toHaveBeenCalledWith('US', expect.any(AbortSignal))
    expect(wrapper.text()).toContain('S&P 500')
    expect(wrapper.text()).toContain('Technology')
    expect(wrapper.text()).toContain('AI infrastructure')
    expect(wrapper.text()).toContain('Provider snapshot news')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('代理覆盖')
    expect(wrapper.text()).toContain('手动研究')
    expect(wrapper.text()).toContain('部分可用')
    expect(wrapper.text()).not.toContain('市场广度、板块、热点、新闻和信号尚未接入该市场')
  })
})
