import { api } from './client'
import type { DataHealth } from './types'

export async function getDataHealth(fast: boolean = false): Promise<DataHealth> {
  return api.get<DataHealth>('/api/datahub/health', { fast: fast ? 'true' : 'false' })
}
