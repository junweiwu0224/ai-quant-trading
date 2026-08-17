import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type MarketCode = 'CN' | 'HK' | 'US' | 'JP' | 'KR' | 'TW'

export interface MarketData {
  symbol: string
  name: string
  price: number
  change: number
  changePct: number
  volume: number
  amount?: number
  open?: number
  high?: number
  low?: number
  preClose?: number
  timestamp: string
  market: MarketCode
}

export interface Quote {
  symbol: string
  price: number
  change: number
  changePct: number
  timestamp: string
  volume?: number
  bid?: number
  ask?: number
  bidSize?: number
  askSize?: number
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

    const data = marketData.value.get(selectedSymbol.value)
    const quote = quotes.value.get(selectedSymbol.value)

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
    return (symbol: string) => marketData.value.has(symbol)
  })

  const hasQuote = computed(() => {
    return (symbol: string) => quotes.value.has(symbol)
  })

  const marketDataList = computed(() => {
    return Array.from(marketData.value.values()).filter(
      data => data.market === selectedMarket.value
    )
  })

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
      // TODO: Replace with actual API call in Task 11
      // const response = await api.getMarketData(market, symbol)
      // const data = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 400))

      // Mock data for development
      const mockData: MarketData = {
        symbol,
        name: symbol.includes('600519') ? '贵州茅台' : symbol,
        price: 1850.50,
        change: 25.30,
        changePct: 1.39,
        volume: 1250000,
        amount: 2312500000,
        open: 1825.20,
        high: 1865.00,
        low: 1820.00,
        preClose: 1825.20,
        timestamp: new Date().toISOString(),
        market
      }

      marketData.value.set(symbol, mockData)
      return mockData
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
      // TODO: Replace with actual API call in Task 11
      // const response = await api.getMultipleMarketData(market, symbols)
      // const dataList = response.data

      // Placeholder: simulate API call
      await new Promise(resolve => setTimeout(resolve, 600))

      const results: MarketData[] = []
      for (const symbol of symbols) {
        const mockData: MarketData = {
          symbol,
          name: symbol,
          price: Math.random() * 1000 + 100,
          change: Math.random() * 10 - 5,
          changePct: Math.random() * 5 - 2.5,
          volume: Math.floor(Math.random() * 10000000),
          timestamp: new Date().toISOString(),
          market
        }
        marketData.value.set(symbol, mockData)
        results.push(mockData)
      }

      return results
    } catch (err) {
      error.value = err instanceof Error ? err.message : '批量加载市场数据失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  function updateQuote(symbol: string, quote: Quote) {
    quotes.value.set(symbol, quote)

    // Update market data if exists
    const data = marketData.value.get(symbol)
    if (data) {
      marketData.value.set(symbol, {
        ...data,
        price: quote.price,
        change: quote.change,
        changePct: quote.changePct,
        volume: quote.volume ?? data.volume,
        timestamp: quote.timestamp
      })
    }
  }

  function updateMultipleQuotes(updates: Quote[]) {
    for (const quote of updates) {
      updateQuote(quote.symbol, quote)
    }
  }

  function getMarketData(symbol: string): MarketData | undefined {
    return marketData.value.get(symbol)
  }

  function getQuote(symbol: string): Quote | undefined {
    return quotes.value.get(symbol)
  }

  function clearMarketData(symbol?: string) {
    if (symbol) {
      marketData.value.delete(symbol)
      quotes.value.delete(symbol)
    } else {
      marketData.value.clear()
      quotes.value.clear()
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
