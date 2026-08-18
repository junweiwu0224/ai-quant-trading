import { createRouter, createWebHistory, type LocationQuery, type LocationQueryRaw, type RouteLocationGeneric, type RouteLocationRaw } from 'vue-router'

// LIVE TRADING DISABLED
// Routes that involve broker connections or live trading
const BROKER_RELATED_ROUTES = [
  '/app/broker',
  '/app/conditional-orders',
  '/app/more/conditional-orders',
  '/app/broker-live',
  '/app/more/broker-live',
  '/app/paper',
  '/app/more/paper',
]

export const legacyHashRoutes: Record<string, string> = {
  overview: '/app/decision',
  intelligence: '/app/intelligence',
  positions: '/app/portfolio-risk',
  'ai-advice': '/app/ai',
  backtest: '/app/validation',
  'strategy-research': '/app/research/alpha',
  paper: '/app/paper',
  alerts: '/app/alerts',
  settings: '/app/settings',
  research: '/app/research',
  trade: '/app/portfolio-risk',
  'strategy-admin': '/app/strategy',
  screener: '/app/research/screener',
  agent: '/app/ai',
  reports: '/app/reports',
  'stock-detail': '/app/research',
  alpha: '/app/research/alpha',
  portfolio: '/app/portfolio',
  sim: '/app/paper',
  strategy: '/app/strategy',
  risk: '/app/risk',
  daily: '/app/reports',
  broker: '/app/broker',
  'broker-live': '/app/broker',
  'ai-runtime': '/app/ai/runtime',
  'conditional-orders': '/app/conditional-orders',
  stock: '/app/research',
}

const routes = [
  { path: '/', redirect: '/app/decision' },
  { path: '/app', redirect: '/app/decision' },
  { path: '/auth', component: () => import('./views/AuthView.vue'), meta: { title: '登录' } },
  { path: '/app/decision', component: () => import('./views/DecisionView.vue'), meta: { title: '决策中心' } },
  { path: '/app/intelligence', component: () => import('./views/IntelligenceView.vue'), meta: { title: '市场情报' } },
  { path: '/app/workflows', component: () => import('./views/WorkflowsView.vue'), meta: { title: '工作流目录' } },
  { path: '/app/reports', component: () => import('./views/ReportsView.vue'), meta: { title: '报告' } },
  { path: '/app/stock-detail', redirect: (to: RouteLocationGeneric) => stockDetailRedirect(to, new URLSearchParams()) },
  { path: '/app/research/screener', component: () => import('./views/ScreenerView.vue'), meta: { title: '条件筛选' } },
  { path: '/app/research/alpha', component: () => import('./views/AlphaFactorsView.vue'), meta: { title: 'Alpha 与因子' } },
  { path: '/app/research/formula-basket', component: () => import('./views/AlphaFactorsView.vue'), meta: { title: '公式与篮子' } },
  { path: '/app/research/:market/:symbol', component: () => import('./views/ResearchView.vue'), meta: { title: '单股研究' } },
  { path: '/app/research', redirect: '/app/research/CN/600519' },
  { path: '/app/validation', component: () => import('./views/ValidationView.vue'), meta: { title: '验证' } },
  { path: '/app/notifications', component: () => import('./views/NotificationsView.vue'), meta: { title: '通知' } },
  { path: '/app/settings', component: () => import('./views/SettingsView.vue'), meta: { title: '设置' } },
  { path: '/app/portfolio-risk', component: () => import('./views/PortfolioRiskView.vue'), meta: { title: '组合风控' } },
  { path: '/app/paper', component: () => import('./views/PaperRiskView.vue'), meta: { title: '模拟盘交易' } },
  { path: '/app/portfolio', component: () => import('./views/more/PortfolioOptView.vue'), meta: { title: '持仓优化' } },
  { path: '/app/risk', component: () => import('./views/more/RiskMonitorView.vue'), meta: { title: '风险监控' } },
  { path: '/app/conditional-orders', component: () => import('./views/ConditionalOrdersView.vue'), meta: { title: '条件单' } },
  { path: '/app/strategy', component: () => import('./views/StrategyWorkbenchView.vue'), meta: { title: '策略工作台' } },
  { path: '/app/alerts', component: () => import('./views/AlertRulesView.vue'), meta: { title: '告警规则' } },
  { path: '/app/ai', component: () => import('./views/AgentOpsView.vue'), meta: { title: 'AI 工作台' } },
  { path: '/app/ai/runtime', component: () => import('./views/more/AIRuntimeView.vue'), meta: { title: 'AI Runtime 配置' } },
  { path: '/app/broker', component: () => import('./views/BrokerLiveView.vue'), meta: { title: 'Broker 安全' } },
  { path: '/app/screener', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/screener', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: '条件筛选' } },
  { path: '/app/alpha', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/alpha', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: 'Alpha 与因子' } },
  { path: '/app/strategies', redirect: (to: RouteLocationGeneric) => ({ path: '/app/strategy', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: '策略工作台' } },
  { path: '/app/agent-ops', redirect: (to: RouteLocationGeneric) => ({ path: '/app/ai', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: 'AI 工作台' } },
  { path: '/app/ai-runtime', redirect: (to: RouteLocationGeneric) => ({ path: '/app/ai/runtime', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: 'AI Runtime 配置' } },
  { path: '/app/broker-live', redirect: (to: RouteLocationGeneric) => ({ path: '/app/broker', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-route') }), meta: { title: 'Broker 安全' } },
  { path: '/app/more/paper', redirect: (to: RouteLocationGeneric) => ({ path: '/app/paper', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/portfolio-risk', redirect: (to: RouteLocationGeneric) => ({ path: '/app/portfolio-risk', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/portfolio', redirect: (to: RouteLocationGeneric) => ({ path: '/app/portfolio', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/risk', redirect: (to: RouteLocationGeneric) => ({ path: '/app/risk', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/conditional-orders', redirect: (to: RouteLocationGeneric) => ({ path: '/app/conditional-orders', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/screener', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/screener', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/alpha', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/alpha', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/alpha-factors', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/alpha', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/formula-basket', redirect: (to: RouteLocationGeneric) => ({ path: '/app/research/formula-basket', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/strategy', redirect: (to: RouteLocationGeneric) => ({ path: '/app/strategy', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/strategies', redirect: (to: RouteLocationGeneric) => ({ path: '/app/strategy', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/agents', redirect: (to: RouteLocationGeneric) => ({ path: '/app/ai', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/agent-ops', redirect: (to: RouteLocationGeneric) => ({ path: '/app/ai', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/ai-runtime', redirect: (to: RouteLocationGeneric) => ({ path: '/app/ai/runtime', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/alerts', redirect: (to: RouteLocationGeneric) => ({ path: '/app/alerts', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/broker-live', redirect: (to: RouteLocationGeneric) => ({ path: '/app/broker', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more', redirect: (to: RouteLocationGeneric) => ({ path: '/app/workflows', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }), meta: { title: '工作流目录' } },
  { path: '/app/more/market-radar', redirect: (to: RouteLocationGeneric) => ({ path: '/app/decision', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/watchlists-alerts', redirect: (to: RouteLocationGeneric) => ({ path: '/app/decision', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/stock-detail', redirect: (to: RouteLocationGeneric) => stockDetailRedirect(to, new URLSearchParams()) },
  { path: '/app/more/strategies-backtest', redirect: (to: RouteLocationGeneric) => ({ path: '/app/strategy', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/daily-briefs', redirect: (to: RouteLocationGeneric) => ({ path: '/app/reports', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/:tool', redirect: (to: RouteLocationGeneric) => ({ path: '/app/workflows', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }), meta: { title: '工作流目录' } }, // redirect: '/app/workflows'
  { path: '/report/:token', component: () => import('./views/SharedReportView.vue'), meta: { title: '完整报告' } },
  { path: '/app/:pathMatch(.*)*', redirect: '/app/decision' },
]

const router = createRouter({ history: createWebHistory('/'), routes, scrollBehavior: () => ({ top: 0 }) })

const supportedMarkets = new Set(['CN', 'HK', 'US', 'JP', 'KR', 'TW'])

function firstQueryValue(query: LocationQuery, key: string): string {
  const value = query[key]
  if (Array.isArray(value)) return String(value[0] || '')
  return value == null ? '' : String(value)
}

function parseLegacyHash(hash: string): { route: string; query: URLSearchParams } {
  const raw = hash.replace(/^#/, '').replace(/^\/+/, '')
  const separator = raw.indexOf('?')
  const routePart = separator === -1 ? raw : raw.slice(0, separator)
  const queryPart = separator === -1 ? '' : raw.slice(separator + 1)
  let route = routePart
  try { route = decodeURIComponent(routePart) } catch { /* malformed legacy links fall back to the default route */ }
  return { route: route.trim().toLowerCase(), query: new URLSearchParams(queryPart) }
}

function mergedLegacyQuery(to: RouteLocationGeneric, legacyQuery: URLSearchParams, source = 'legacy-hash'): LocationQueryRaw {
  const merged: Record<string, string> = {}
  for (const [key, value] of Object.entries(to.query)) {
    if (Array.isArray(value)) {
      if (value[0] != null) merged[key] = String(value[0])
    } else if (value != null) {
      merged[key] = String(value)
    }
  }
  legacyQuery.forEach((value, key) => { merged[key] = value })
  if (!merged.source) merged.source = source
  return merged
}

function stockDetailRedirect(to: RouteLocationGeneric, legacyQuery: URLSearchParams): RouteLocationRaw {
  const code = legacyQuery.get('code') || legacyQuery.get('symbol') || firstQueryValue(to.query, 'code') || firstQueryValue(to.query, 'symbol') || '600519'
  const requestedMarket = legacyQuery.get('market') || firstQueryValue(to.query, 'market')
  const normalizedMarket = String(requestedMarket || '').toUpperCase()
  const market = supportedMarkets.has(normalizedMarket) ? normalizedMarket : 'CN'
  const source = legacyQuery.get('source') || firstQueryValue(to.query, 'source') || 'legacy-hash'
  return { path: `/app/research/${market}/${encodeURIComponent(code)}`, query: { code, market, source } }
}

function legacyRouteFromQuery(to: RouteLocationGeneric): string {
  return (firstQueryValue(to.query, 'route') || firstQueryValue(to.query, 'tab') || firstQueryValue(to.query, 'view') || firstQueryValue(to.query, 'page')).trim().toLowerCase()
}

function resolveLegacyHashRedirect(to: RouteLocationGeneric): RouteLocationRaw | null {
  if (!['/', '/app', '/app/decision'].includes(to.path)) return null

  const hash = to.hash.replace(/^#/, '')
  const { route: legacyRoute, query: legacyQuery } = parseLegacyHash(hash)
  if (legacyRoute === 'stock-detail') return stockDetailRedirect(to, legacyQuery)
  if (legacyRoute === 'stock') return stockDetailRedirect(to, legacyQuery)

  const resolvedRoute = legacyRoute || legacyRouteFromQuery(to)
  const target = legacyHashRoutes[resolvedRoute]
  if (target && target !== to.path) return { path: target, query: mergedLegacyQuery(to, legacyQuery) }

  if (to.path === '/app/decision') {
    const symbol = firstQueryValue(to.query, 'symbol') || firstQueryValue(to.query, 'code') || legacyRoute.match(/\d{6}/)?.[0] || ''
    if (symbol) return stockDetailRedirect(to, legacyQuery)
  }
  return null
}

router.beforeEach((to) => {
  if (to.path.startsWith('/report/')) {
    document.title = `${String(to.meta.title || '完整报告')} · 决策工作台`
    return true
  }

  const legacyRedirect = resolveLegacyHashRedirect(to)
  if (legacyRedirect) return legacyRedirect

  // LIVE TRADING DISABLED
  // Mark broker-related routes for the guard component
  if (BROKER_RELATED_ROUTES.includes(to.path)) {
    // The BrokerDisableGuard component will handle showing the warning
    // on first visit to these pages
  }

  document.title = `${String(to.meta.title || 'AI Quant')} · 决策工作台`
})

export default router
