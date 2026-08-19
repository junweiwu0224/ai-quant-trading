import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import router from './router'
import { workspaceForPath } from './navigation/workflows'

describe('Vue route compatibility', () => {
  beforeAll(() => {
    window.scrollTo = () => undefined
  })

  beforeEach(async () => {
    await router.push('/app/decision')
  })

  it('preserves a legacy symbol and market when entering research', async () => {
    await router.push('/app/decision?code=600519&market=US')
    expect(router.currentRoute.value.path).toBe('/app/research/US/600519')
    expect(router.currentRoute.value.query).toMatchObject({ source: 'legacy-hash', market: 'US' })
  })

  it('keeps reports outside the authenticated workspace shell', async () => {
    await router.push('/report/share-token')
    expect(router.currentRoute.value.path).toBe('/report/share-token')
  })

  it('maps old aliases and keeps their query context', async () => {
    await router.push('/app/decision#alpha?code=600519&market=US')
    expect(router.currentRoute.value.path).toBe('/app/research/alpha')
    expect(router.currentRoute.value.query).toMatchObject({ code: '600519', market: 'US', source: 'legacy-hash' })
  })

  it('accepts a legacy route query when a server serves the Vue shell at root', async () => {
    await router.push('/app/decision?route=portfolio&market=CN')
    expect(router.currentRoute.value.path).toBe('/app/portfolio')
    expect(router.currentRoute.value.query).toMatchObject({ route: 'portfolio', market: 'CN', source: 'legacy-hash' })
  })

  it('treats the old stock alias as a contextual research route', async () => {
    await router.push('/app/decision#stock?code=AAPL&market=US')
    expect(router.currentRoute.value.path).toBe('/app/research/US/AAPL')
    expect(router.currentRoute.value.query).toMatchObject({ code: 'AAPL', market: 'US', source: 'legacy-hash' })
  })

  it('routes a More matrix alias to its canonical Vue workflow', async () => {
    await router.push('/app/more/market-radar?market=CN')
    expect(router.currentRoute.value.path).toBe('/app/decision')
    expect(router.currentRoute.value.query).toMatchObject({ market: 'CN', source: 'legacy-more' })
  })

  it('keeps symbol context when an old More stock-detail alias is opened', async () => {
    await router.push('/app/more/stock-detail?code=AAPL&market=US&source=matrix')
    expect(router.currentRoute.value.path).toBe('/app/research/US/AAPL')
    expect(router.currentRoute.value.query).toEqual({ code: 'AAPL', market: 'US', source: 'matrix' })
  })

  it('maps every canonical workflow into a visible workspace', () => {
    expect(workspaceForPath('/app/intelligence')?.id).toBe('decision')
    expect(workspaceForPath('/app/research/US/AAPL')?.id).toBe('research')
    expect(workspaceForPath('/app/ai')?.id).toBe('research')
    expect(workspaceForPath('/app/strategy')?.id).toBe('validation')
    expect(workspaceForPath('/app/paper')?.id).toBe('portfolio')
    expect(workspaceForPath('/app/notifications')?.id).toBe('reports')
    expect(workspaceForPath('/app/settings')).toBeNull()
  })
})
