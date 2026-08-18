import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'
type NullableNumber = number | null

export interface MarketData {
  symbol: string
  name: string
  price: NullableNumber
  change: NullableNumber
  changePct: NullableNumber
  volume: NullableNumber
  amount?: NullableNumber
  open?: NullableNumber
  high?: NullableNumber
  low?: NullableNumber
  preClose?: NullableNumber
  timestamp: string | null
  market: MarketCode
}

export interface Quote {
  symbol: string
  name?: string
  price: NullableNumber
  change: NullableNumber
  changePct: NullableNumber
  timestamp: string | null
  volume?: NullableNumber
  amount?: NullableNumber
  bid?: NullableNumber
  ask?: NullableNumber
  bidSize?: NullableNumber
  askSize?: NullableNumber
  open?: NullableNumber
  high?: NullableNumber
  low?: NullableNumber
  preClose?: NullableNumber
  market: MarketCode
}

export interface MarketInfo {
  code: MarketCode
  name: string
  timezone: string
  currency: string
  tradingHours: {
    open: string
    close: string
  }
  isOpen: boolean
}

export const useMarketStore = defineStore('market', () => {
  const selectedMarket = ref<MarketCode>('CN')
  const selectedSymbol = ref<string | null>(null)
  const marketData = ref<Map<string, MarketData>>(new Map())
  const quotes = ref<Map<string, Quote>>(new Map())
  const loading = ref(false)
  const error = ref<string | null>(null)

  const markets: Record<MarketCode, MarketInfo> = {
    CN: {
      code: 'CN',
      name: 'A股',
      timezone: 'Asia/Shanghai',
      currency: 'CNY',
      tradingHours: { open: '09:30', close: '15:00' },
      isOpen: false
    },
    HK: {
      code: 'HK',
      name: '港股',
      timezone: 'Asia/Hong_Kong',
      currency: 'HKD',
      tradingHours: { open: '09:30', close: '16:00' },
      isOpen: false
    },
    US: {
      code: 'US',
      name: '美股',
      timezone: 'America/New_York',
      currency: 'USD',
      tradingHours: { open: '09:30', close: '16:00' },
      isOpen: false
    },
    JP: {
      code: 'JP',
      name: '日本',
      timezone: 'Asia/Tokyo',
      currency: 'JPY',
      tradingHours: { open: '09:00', close: '15:00' },
      isOpen: false
    },
    KR: {
      code: 'KR',
      name: '韩国',
      timezone: 'Asia/Seoul',
      currency: 'KRW',
      tradingHours: { open: '09:00', close: '15:30' },
      isOpen: false
    },
    TW: {
      code: 'TW',
      name: '台湾',
      timezone: 'Asia/Taipei',
      currency: 'TWD',
      tradingHours: { open: '09:00', close: '13:30' },
      isOpen: false
    }
  }

  const currentMarket = computed(() => markets[selectedMarket.value])

  const currentStock = computed(() => {
    if (!selectedSymbol.value) return null

    const data = marketData.value.get(cacheKey(selectedMarket.value, selectedSymbol.value))
    const quote = quotes.value.get(cacheKey(selectedMarket.value, selectedSymbol.value))

    return {
      symbol: selectedSymbol.value,
      market: selectedMarket.value,
      data,
      quote,
      hasData: Boolean(data),
      hasQuote: Boolean(quote)
    }
  })

  const hasData = computed(() => {
    return (symbol: string, market: MarketCode = selectedMarket.value) => marketData.value.has(cacheKey(market, symbol))
  })

  const hasQuote = computed(() => {
    return (symbol: string, market: MarketCode = selectedMarket.value) => quotes.value.has(cacheKey(market, symbol))
  })

  const marketDataList = computed(() => {
    return Array.from(marketData.value.values()).filter(
      data => data.market === selectedMarket.value
    )
  })

  function cacheKey(market: MarketCode, symbol: string): string {
    return `${market}:${symbol.trim().toUpperCase()}`
  }

  function nullableNumber(value: unknown): NullableNumber {
    if (value === null || value === undefined || value === '') return null
    const number = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(number) ? number : null
  }

  function normalizedTimestamp(value: unknown): string | null {
    if (value === null || value === undefined || value === '') return null
    if (typeof value === 'number' || (typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value.trim()))) {
      const numeric = Number(value)
      if (!Number.isFinite(numeric)) return null
      const milliseconds = Math.abs(numeric) < 100_000_000_000 ? numeric * 1000 : numeric
      const date = new Date(milliseconds)
      return Number.isNaN(date.getTime()) ? null : date.toISOString()
    }
    const date = new Date(String(value))
    return Number.isNaN(date.getTime()) ? null : date.toISOString()
  }

  function normalizeQuote(raw: unknown, symbol: string, market: MarketCode): Quote {
    const value = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
    return {
      symbol: String(value.code || value.symbol || symbol),
      name: typeof value.name === 'string' && value.name.trim() ? value.name : undefined,
      price: nullableNumber(value.price),
      change: nullableNumber(value.change),
      changePct: nullableNumber(value.change_pct ?? value.changePct),
      timestamp: normalizedTimestamp(value.timestamp ?? value.updated_at ?? value.as_of),
      volume: nullableNumber(value.volume),
      amount: nullableNumber(value.amount),
      bid: nullableNumber(value.bid),
      ask: nullableNumber(value.ask),
      bidSize: nullableNumber(value.bid_size ?? value.bidSize),
      askSize: nullableNumber(value.ask_size ?? value.askSize),
      open: nullableNumber(value.open),
      high: nullableNumber(value.high),
      low: nullableNumber(value.low),
      preClose: nullableNumber(value.pre_close ?? value.preClose),
      market
    }
  }

  function setMarket(market: MarketCode) {
    selectedMarket.value = market
    error.value = null
  }

  function setSymbol(symbol: string | null) {
    selectedSymbol.value = symbol
    error.value = null
  }

  async function fetchMarketData(market: MarketCode, symbol: string) {
    loading.value = true
    error.value = null
    try {
      const { getStockQuote } = await import('../api/market')
      const quote = normalizeQuote(await getStockQuote(symbol, market), symbol, market)

      const data: MarketData = {
        symbol: quote.symbol,
        name: quote.name || symbol,
        price: quote.price,
        change: quote.change,
        changePct: quote.changePct,
        volume: quote.volume ?? null,
        amount: quote.amount ?? null,
        open: quote.open,
        high: quote.high,
        low: quote.low,
        preClose: quote.preClose,
        timestamp: quote.timestamp,
        market
      }

      marketData.value.set(cacheKey(market, symbol), data)
      return data
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载市场数据失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchMultipleMarketData(market: MarketCode, symbols: string[]) {
    loading.value = true
    error.value = null
    try {
      const { getStockQuote } = await import('../api/market')

      // Fetch quotes in parallel
      const results = await Promise.allSettled(
        symbols.map(symbol => getStockQuote(symbol, market))
      )

      const marketDataList: MarketData[] = []

      for (let i = 0; i < results.length; i++) {
        const result = results[i]
        const symbol = symbols[i]

        if (result.status === 'fulfilled') {
          const quote = normalizeQuote(result.value, symbol, market)
          const data: MarketData = {
            symbol: quote.symbol,
            name: quote.name || symbol,
            price: quote.price,
            change: quote.change,
            changePct: quote.changePct,
            volume: quote.volume ?? null,
            amount: quote.amount ?? null,
            open: quote.open,
            high: quote.high,
            low: quote.low,
            preClose: quote.preClose,
            timestamp: quote.timestamp,
            market
          }
          marketData.value.set(cacheKey(market, symbol), data)
          marketDataList.push(data)
        } else {
          console.warn(`Failed to fetch data for ${symbol}:`, result.reason)
        }
      }

      return marketDataList
    } catch (err) {
      error.value = err instanceof Error ? err.message : '批量加载市场数据失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  function updateQuote(symbol: string, quote: Quote) {
    const market = quote.market || selectedMarket.value
    const normalized = normalizeQuote(quote, symbol, market)
    const key = cacheKey(market, symbol)
    quotes.value.set(key, normalized)

    // Update market data if exists
    const data = marketData.value.get(key)
    if (data) {
      marketData.value.set(key, {
        ...data,
        price: normalized.price,
        change: normalized.change,
        changePct: normalized.changePct,
        volume: normalized.volume ?? data.volume,
        timestamp: normalized.timestamp
      })
    }
  }

  function updateMultipleQuotes(updates: Quote[]) {
    for (const quote of updates) {
      updateQuote(quote.symbol, quote)
    }
  }

  function getMarketData(symbol: string, market: MarketCode = selectedMarket.value): MarketData | undefined {
    return marketData.value.get(cacheKey(market, symbol))
  }

  function getQuote(symbol: string, market: MarketCode = selectedMarket.value): Quote | undefined {
    return quotes.value.get(cacheKey(market, symbol))
  }

  function clearMarketData(symbol?: string, market: MarketCode = selectedMarket.value) {
    if (symbol) {
      const key = cacheKey(market, symbol)
      marketData.value.delete(key)
      quotes.value.delete(key)
    } else {
      const prefix = `${market}:`
      for (const key of marketData.value.keys()) if (key.startsWith(prefix)) marketData.value.delete(key)
      for (const key of quotes.value.keys()) if (key.startsWith(prefix)) quotes.value.delete(key)
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    selectedMarket,
    selectedSymbol,
    marketData,
    quotes,
    loading,
    error,
    markets,
    currentMarket,
    currentStock,
    hasData,
    hasQuote,
    marketDataList,
    setMarket,
    setSymbol,
    fetchMarketData,
    fetchMultipleMarketData,
    updateQuote,
    updateMultipleQuotes,
    getMarketData,
    getQuote,
    clearMarketData,
    clearError
  }
})
