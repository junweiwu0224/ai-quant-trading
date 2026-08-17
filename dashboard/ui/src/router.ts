import { createRouter, createWebHistory, type LocationQuery, type LocationQueryRaw, type RouteLocationGeneric, type RouteLocationRaw } from 'vue-router'

export const legacyHashRoutes: Record<string, string> = {
  overview: '/app/decision',
  intelligence: '/app/intelligence',
  positions: '/app/more/portfolio-risk',
  'ai-advice': '/app/more/agents',
  backtest: '/app/validation',
  'strategy-research': '/app/more/alpha-factors',
  paper: '/app/more/paper',
  alerts: '/app/more/alerts',
  settings: '/app/settings',
  research: '/app/more',
  trade: '/app/more/portfolio-risk',
  'strategy-admin': '/app/more/strategies',
  screener: '/app/more/screener',
  agent: '/app/more/agents',
  reports: '/app/reports',
  'stock-detail': '/app/research',
  alpha: '/app/more/alpha-factors',
  portfolio: '/app/more/portfolio-risk',
  sim: '/app/more/paper',
  strategy: '/app/more/strategies',
  risk: '/app/more/portfolio-risk',
  daily: '/app/more',
  stock: '/app/research',
}

const routes = [
  { path: '/', redirect: '/app/decision' },
  { path: '/app', redirect: '/app/decision' },
  { path: '/auth', component: () => import('./views/AuthView.vue'), meta: { title: '登录' } },
  { path: '/app/decision', component: () => import('./views/DecisionView.vue'), meta: { title: '决策中心' } },
  { path: '/app/intelligence', component: () => import('./views/IntelligenceView.vue'), meta: { title: '市场情报' } },
  { path: '/app/reports', component: () => import('./views/ReportsView.vue'), meta: { title: '报告' } },
  { path: '/app/stock-detail', redirect: (to: RouteLocationGeneric) => stockDetailRedirect(to, new URLSearchParams()) },
  { path: '/app/research/:market/:symbol', component: () => import('./views/ResearchView.vue'), meta: { title: '单股研究' } },
  { path: '/app/research', redirect: '/app/research/CN/600519' },
  { path: '/app/validation', component: () => import('./views/ValidationView.vue'), meta: { title: '验证' } },
  { path: '/app/notifications', component: () => import('./views/NotificationsView.vue'), meta: { title: '通知' } },
  { path: '/app/settings', component: () => import('./views/SettingsView.vue'), meta: { title: '设置' } },
  { path: '/app/more/screener', component: () => import('./views/ScreenerView.vue'), meta: { title: '条件筛选' } },
  { path: '/app/more/portfolio-risk', component: () => import('./views/PortfolioRiskView.vue'), meta: { title: '组合风控' } },
  { path: '/app/more/paper', component: () => import('./views/more/PaperTradingView.vue'), meta: { title: '模拟盘交易' } },
  { path: '/app/more/portfolio', component: () => import('./views/more/PortfolioOptView.vue'), meta: { title: '持仓优化' } },
  { path: '/app/more/risk', component: () => import('./views/more/RiskMonitorView.vue'), meta: { title: '风险监控' } },
  { path: '/app/more/conditional-orders', component: () => import('./views/more/ConditionalOrdersView.vue'), meta: { title: '条件单' } },
  { path: '/app/more/alpha', component: () => import('./views/more/AlphaFactorsView.vue'), meta: { title: 'Alpha 因子' } },
  { path: '/app/more/strategy', component: () => import('./views/more/StrategyWorkbenchView.vue'), meta: { title: '策略工作台' } },
  { path: '/app/more/agent-ops', component: () => import('./views/more/AgentOpsView.vue'), meta: { title: 'Agent 运维' } },
  { path: '/app/more/ai-runtime', component: () => import('./views/more/AIRuntimeView.vue'), meta: { title: 'AI Runtime 配置' } },
  { path: '/app/more/alerts', component: () => import('./views/AlertRulesView.vue'), meta: { title: '告警规则' } },
  { path: '/app/more/strategies', component: () => import('./views/StrategyWorkbenchView.vue'), meta: { title: '策略工作台' } },
  { path: '/app/more/alpha-factors', component: () => import('./views/AlphaFactorsView.vue'), meta: { title: 'Alpha 与因子' } },
  { path: '/app/more/formula-basket', component: () => import('./views/AlphaFactorsView.vue'), meta: { title: '公式与篮子' } },
  { path: '/app/more/broker-live', component: () => import('./views/BrokerLiveView.vue'), meta: { title: 'Broker 与实盘' } },
  { path: '/app/more/agents', component: () => import('./views/AgentOpsView.vue'), meta: { title: 'Agent 操作' } },
  { path: '/app/more', component: () => import('./views/MoreView.vue'), meta: { title: '更多' } },
  { path: '/app/more/market-radar', redirect: (to: RouteLocationGeneric) => ({ path: '/app/decision', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/watchlists-alerts', redirect: (to: RouteLocationGeneric) => ({ path: '/app/decision', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/stock-detail', redirect: (to: RouteLocationGeneric) => stockDetailRedirect(to, new URLSearchParams()) },
  { path: '/app/more/strategies-backtest', redirect: (to: RouteLocationGeneric) => ({ path: '/app/more/strategies', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/daily-briefs', redirect: (to: RouteLocationGeneric) => ({ path: '/app/reports', query: mergedLegacyQuery(to, new URLSearchParams(), 'legacy-more') }) },
  { path: '/app/more/:tool', redirect: '/app/more' },
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

  document.title = `${String(to.meta.title || 'AI Quant')} · 决策工作台`
})

export default router
