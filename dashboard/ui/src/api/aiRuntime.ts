/**
 * AI Runtime API
 * Manages AI model configuration, token usage, and runtime status
 */

import { api } from './client'
import type { ApiEnvelope } from './types'

export type ModelProvider = 'openai' | 'anthropic' | 'azure' | 'custom'
export type ModelStatus = 'online' | 'degraded' | 'offline'
export type ApiKeyStatus = 'valid' | 'invalid' | 'expired' | 'not-set'

export interface ModelConfig {
  id: string
  name: string
  provider: ModelProvider
  modelId: string
  status: ModelStatus
  apiKeyStatus: ApiKeyStatus
  requestsToday: number
  tokensToday: number
  costToday: number
  enabled: boolean
  maxTokens?: number
  temperature?: number
  topP?: number
  lastUsedAt?: string
  metadata?: Record<string, unknown>
}

export interface ApiKey {
  id: string
  provider: ModelProvider
  maskedKey: string
  status: ApiKeyStatus
  createdAt: string
  lastUsedAt?: string
  expiresAt?: string
}

export interface TokenUsageData {
  date: string
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cost: number
  requests: number
}

export interface CostBreakdown {
  model: string
  provider: ModelProvider
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cost: number
  requests: number
  percentage: number
}

export interface AIRuntimeStatus {
  totalModels: number
  activeModels: number
  totalRequests: number
  totalTokens: number
  totalCost: number
  healthStatus: 'healthy' | 'degraded' | 'down'
  lastUpdatedAt: string
}

/**
 * Get AI runtime status overview
 */
export async function getAIRuntimeStatus(): Promise<AIRuntimeStatus> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/ai/runtime/status')

  await new Promise(resolve => setTimeout(resolve, 300))
  return mockRuntimeStatus()
}

/**
 * Get all model configurations
 */
export async function getModelConfigs(): Promise<ModelConfig[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/ai/runtime/models')

  await new Promise(resolve => setTimeout(resolve, 350))
  return mockModelConfigs()
}

/**
 * Get token usage history
 */
export async function getTokenUsageHistory(days: number = 30): Promise<TokenUsageData[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get(`/api/ai/runtime/usage?days=${days}`)

  await new Promise(resolve => setTimeout(resolve, 400))
  return mockTokenUsageHistory(days)
}

/**
 * Get cost breakdown by model
 */
export async function getCostBreakdown(): Promise<CostBreakdown[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/ai/runtime/costs')

  await new Promise(resolve => setTimeout(resolve, 300))
  return mockCostBreakdown()
}

/**
 * Get API keys (DISABLED for modification)
 */
export async function getApiKeys(): Promise<ApiKey[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get('/api/ai/runtime/keys')

  await new Promise(resolve => setTimeout(resolve, 250))
  return mockApiKeys()
}

/**
 * Test API key connection (DISABLED)
 */
export async function testApiKey(provider: ModelProvider): Promise<{ success: boolean; message: string }> {
  // LIVE TRADING DISABLED - This would test real API connections
  throw new Error('API 密钥测试功能已禁用')
}

/**
 * Update API key (DISABLED)
 */
export async function updateApiKey(provider: ModelProvider, key: string): Promise<void> {
  // LIVE TRADING DISABLED - This would update real API keys
  throw new Error('API 密钥修改功能已禁用')
}

/**
 * Update model configuration (DISABLED)
 */
export async function updateModelConfig(modelId: string, config: Partial<ModelConfig>): Promise<ModelConfig> {
  // LIVE TRADING DISABLED
  throw new Error('模型配置修改功能已禁用')
}

// ==================== Mock Data ====================

function mockRuntimeStatus(): AIRuntimeStatus {
  return {
    totalModels: 4,
    activeModels: 3,
    totalRequests: 12547,
    totalTokens: 8425630,
    totalCost: 142.38,
    healthStatus: 'healthy',
    lastUpdatedAt: new Date().toISOString(),
  }
}

function mockModelConfigs(): ModelConfig[] {
  return [
    {
      id: 'gpt-4-turbo',
      name: 'GPT-4 Turbo',
      provider: 'openai',
      modelId: 'gpt-4-turbo-preview',
      status: 'online',
      apiKeyStatus: 'valid',
      requestsToday: 127,
      tokensToday: 85420,
      costToday: 1.28,
      enabled: true,
      maxTokens: 4096,
      temperature: 0.7,
      topP: 1,
      lastUsedAt: new Date(Date.now() - 180000).toISOString(),
    },
    {
      id: 'claude-3-sonnet',
      name: 'Claude 3 Sonnet',
      provider: 'anthropic',
      modelId: 'claude-3-sonnet-20240229',
      status: 'online',
      apiKeyStatus: 'valid',
      requestsToday: 89,
      tokensToday: 62350,
      costToday: 0.94,
      enabled: true,
      maxTokens: 4096,
      temperature: 0.7,
      lastUsedAt: new Date(Date.now() - 320000).toISOString(),
    },
    {
      id: 'gpt-3.5-turbo',
      name: 'GPT-3.5 Turbo',
      provider: 'openai',
      modelId: 'gpt-3.5-turbo',
      status: 'online',
      apiKeyStatus: 'valid',
      requestsToday: 456,
      tokensToday: 124680,
      costToday: 0.19,
      enabled: true,
      maxTokens: 4096,
      temperature: 0.8,
      lastUsedAt: new Date(Date.now() - 45000).toISOString(),
    },
    {
      id: 'claude-3-opus',
      name: 'Claude 3 Opus',
      provider: 'anthropic',
      modelId: 'claude-3-opus-20240229',
      status: 'degraded',
      apiKeyStatus: 'valid',
      requestsToday: 12,
      tokensToday: 45210,
      costToday: 3.42,
      enabled: false,
      maxTokens: 4096,
      temperature: 0.6,
      lastUsedAt: new Date(Date.now() - 7200000).toISOString(),
      metadata: { degradedReason: 'Rate limit approaching' },
    },
  ]
}

function mockTokenUsageHistory(days: number): TokenUsageData[] {
  const data: TokenUsageData[] = []
  const now = Date.now()

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now - i * 24 * 60 * 60 * 1000)
    const baseTokens = 50000 + Math.random() * 100000
    const inputTokens = Math.floor(baseTokens * 0.6)
    const outputTokens = Math.floor(baseTokens * 0.4)

    data.push({
      date: date.toISOString().split('T')[0],
      inputTokens,
      outputTokens,
      totalTokens: inputTokens + outputTokens,
      cost: Number(((inputTokens * 0.001 + outputTokens * 0.002) / 1000).toFixed(2)),
      requests: Math.floor(100 + Math.random() * 400),
    })
  }

  return data
}

function mockCostBreakdown(): CostBreakdown[] {
  return [
    {
      model: 'GPT-4 Turbo',
      provider: 'openai',
      inputTokens: 1245000,
      outputTokens: 856000,
      totalTokens: 2101000,
      cost: 52.48,
      requests: 3420,
      percentage: 36.9,
    },
    {
      model: 'Claude 3 Sonnet',
      provider: 'anthropic',
      inputTokens: 985000,
      outputTokens: 642000,
      totalTokens: 1627000,
      cost: 28.45,
      requests: 2680,
      percentage: 20.0,
    },
    {
      model: 'GPT-3.5 Turbo',
      provider: 'openai',
      inputTokens: 3245000,
      outputTokens: 1856000,
      totalTokens: 5101000,
      cost: 9.58,
      requests: 5234,
      percentage: 6.7,
    },
    {
      model: 'Claude 3 Opus',
      provider: 'anthropic',
      inputTokens: 425000,
      outputTokens: 312000,
      totalTokens: 737000,
      cost: 51.87,
      requests: 1213,
      percentage: 36.4,
    },
  ]
}

function mockApiKeys(): ApiKey[] {
  return [
    {
      id: 'key_001',
      provider: 'openai',
      maskedKey: 'sk-proj-...xY2z',
      status: 'valid',
      createdAt: '2024-01-01T00:00:00Z',
      lastUsedAt: new Date(Date.now() - 180000).toISOString(),
    },
    {
      id: 'key_002',
      provider: 'anthropic',
      maskedKey: 'sk-ant-...aB3c',
      status: 'valid',
      createdAt: '2024-01-05T00:00:00Z',
      lastUsedAt: new Date(Date.now() - 320000).toISOString(),
    },
    {
      id: 'key_003',
      provider: 'azure',
      maskedKey: '••••••••...dE4f',
      status: 'not-set',
      createdAt: '2024-01-10T00:00:00Z',
    },
  ]
}
