/**
 * Agent Operations API - Mock implementation for agent monitoring
 *
 * IMPORTANT: This is CLIENT-SIDE SIMULATION ONLY
 * All agent data is mocked for demonstration purposes
 */

import { api } from './client'

// ==================== Types ====================

export interface AgentStatus {
  total_agents: number
  active_agents: number
  idle_agents: number
  error_agents: number
  tasks_running: number
  tasks_queued: number
  tasks_completed_today: number
  success_rate: number
  avg_task_duration: number
}

export interface AgentTask {
  id: string
  agent_id: string
  agent_name: string
  task_type: 'data_collection' | 'analysis' | 'trading' | 'monitoring' | 'research'
  description: string
  status: 'running' | 'queued' | 'completed' | 'failed'
  priority: 'high' | 'normal' | 'low'
  start_time?: string
  end_time?: string
  duration?: number
  progress?: number
  error?: string
}

export interface AgentLog {
  id: string
  timestamp: string
  agent_id: string
  agent_name: string
  level: 'info' | 'warning' | 'error' | 'debug'
  message: string
  task_id?: string
}

export interface Agent {
  id: string
  name: string
  type: 'collector' | 'analyzer' | 'trader' | 'monitor'
  status: 'active' | 'idle' | 'error' | 'stopped'
  current_task?: string
  tasks_completed: number
  uptime: number
  last_active: string
}

// ==================== Mock Data ====================

const mockAgentStatus: AgentStatus = {
  total_agents: 8,
  active_agents: 5,
  idle_agents: 2,
  error_agents: 1,
  tasks_running: 3,
  tasks_queued: 7,
  tasks_completed_today: 124,
  success_rate: 94.5,
  avg_task_duration: 85
}

const mockAgents: Agent[] = [
  {
    id: 'a1',
    name: '市场数据采集器',
    type: 'collector',
    status: 'active',
    current_task: '采集沪深300成分股行情',
    tasks_completed: 1847,
    uptime: 345600,
    last_active: new Date(Date.now() - 30000).toISOString()
  },
  {
    id: 'a2',
    name: '技术指标分析器',
    type: 'analyzer',
    status: 'active',
    current_task: '计算MACD指标',
    tasks_completed: 2156,
    uptime: 342000,
    last_active: new Date(Date.now() - 15000).toISOString()
  },
  {
    id: 'a3',
    name: '风险监控器',
    type: 'monitor',
    status: 'idle',
    tasks_completed: 892,
    uptime: 340800,
    last_active: new Date(Date.now() - 120000).toISOString()
  },
  {
    id: 'a4',
    name: '新闻情感分析',
    type: 'analyzer',
    status: 'active',
    current_task: '分析财经新闻情感',
    tasks_completed: 1523,
    uptime: 320400,
    last_active: new Date(Date.now() - 5000).toISOString()
  },
  {
    id: 'a5',
    name: '订单执行器',
    type: 'trader',
    status: 'error',
    tasks_completed: 456,
    uptime: 280000,
    last_active: new Date(Date.now() - 1800000).toISOString()
  }
]

const mockTasks: AgentTask[] = [
  {
    id: 't1',
    agent_id: 'a1',
    agent_name: '市场数据采集器',
    task_type: 'data_collection',
    description: '采集沪深300成分股实时行情数据',
    status: 'running',
    priority: 'high',
    start_time: new Date(Date.now() - 45000).toISOString(),
    progress: 68
  },
  {
    id: 't2',
    agent_id: 'a2',
    agent_name: '技术指标分析器',
    task_type: 'analysis',
    description: '计算3000+股票的技术指标',
    status: 'running',
    priority: 'normal',
    start_time: new Date(Date.now() - 120000).toISOString(),
    progress: 42
  },
  {
    id: 't3',
    agent_id: 'a4',
    agent_name: '新闻情感分析',
    task_type: 'analysis',
    description: '分析今日财经新闻情感倾向',
    status: 'running',
    priority: 'normal',
    start_time: new Date(Date.now() - 30000).toISOString(),
    progress: 85
  },
  {
    id: 't4',
    agent_id: 'a1',
    agent_name: '市场数据采集器',
    task_type: 'data_collection',
    description: '获取北向资金流向数据',
    status: 'queued',
    priority: 'high'
  },
  {
    id: 't5',
    agent_id: 'a2',
    agent_name: '技术指标分析器',
    task_type: 'analysis',
    description: '更新动量因子数据',
    status: 'queued',
    priority: 'normal'
  },
  {
    id: 't6',
    agent_id: 'a3',
    agent_name: '风险监控器',
    task_type: 'monitoring',
    description: '持仓风险检查',
    status: 'completed',
    priority: 'high',
    start_time: new Date(Date.now() - 180000).toISOString(),
    end_time: new Date(Date.now() - 120000).toISOString(),
    duration: 60
  },
  {
    id: 't7',
    agent_id: 'a5',
    agent_name: '订单执行器',
    task_type: 'trading',
    description: '执行网格交易订单',
    status: 'failed',
    priority: 'high',
    start_time: new Date(Date.now() - 1800000).toISOString(),
    end_time: new Date(Date.now() - 1799000).toISOString(),
    duration: 1,
    error: '连接券商API失败: timeout'
  },
  {
    id: 't8',
    agent_id: 'a4',
    agent_name: '新闻情感分析',
    task_type: 'research',
    description: '研报关键词提取',
    status: 'queued',
    priority: 'low'
  }
]

const mockLogs: AgentLog[] = [
  {
    id: 'l1',
    timestamp: new Date(Date.now() - 10000).toISOString(),
    agent_id: 'a1',
    agent_name: '市场数据采集器',
    level: 'info',
    message: '成功获取300支股票行情数据',
    task_id: 't1'
  },
  {
    id: 'l2',
    timestamp: new Date(Date.now() - 25000).toISOString(),
    agent_id: 'a2',
    agent_name: '技术指标分析器',
    level: 'info',
    message: '开始计算MACD指标，预计需要2分钟',
    task_id: 't2'
  },
  {
    id: 'l3',
    timestamp: new Date(Date.now() - 35000).toISOString(),
    agent_id: 'a4',
    agent_name: '新闻情感分析',
    level: 'info',
    message: '已处理128条新闻，正面情绪占比65%',
    task_id: 't3'
  },
  {
    id: 'l4',
    timestamp: new Date(Date.now() - 60000).toISOString(),
    agent_id: 'a3',
    agent_name: '风险监控器',
    level: 'warning',
    message: '检测到持仓集中度较高，建议分散投资',
    task_id: 't6'
  },
  {
    id: 'l5',
    timestamp: new Date(Date.now() - 120000).toISOString(),
    agent_id: 'a3',
    agent_name: '风险监控器',
    level: 'info',
    message: '完成风险检查，所有指标正常',
    task_id: 't6'
  },
  {
    id: 'l6',
    timestamp: new Date(Date.now() - 180000).toISOString(),
    agent_id: 'a1',
    agent_name: '市场数据采集器',
    level: 'info',
    message: '数据采集任务启动成功',
    task_id: 't1'
  },
  {
    id: 'l7',
    timestamp: new Date(Date.now() - 1799000).toISOString(),
    agent_id: 'a5',
    agent_name: '订单执行器',
    level: 'error',
    message: '连接券商API失败: Connection timeout after 30s',
    task_id: 't7'
  },
  {
    id: 'l8',
    timestamp: new Date(Date.now() - 240000).toISOString(),
    agent_id: 'a2',
    agent_name: '技术指标分析器',
    level: 'debug',
    message: '缓存命中率: 85%, 内存使用: 256MB',
    task_id: 't2'
  },
  {
    id: 'l9',
    timestamp: new Date(Date.now() - 300000).toISOString(),
    agent_id: 'a4',
    agent_name: '新闻情感分析',
    level: 'info',
    message: 'NLP模型加载完成，准备就绪',
    task_id: 't3'
  },
  {
    id: 'l10',
    timestamp: new Date(Date.now() - 360000).toISOString(),
    agent_id: 'a1',
    agent_name: '市场数据采集器',
    level: 'warning',
    message: 'API限流触发，等待30秒后重试',
    task_id: 't1'
  }
]

// ==================== API Functions ====================

export async function getAgentStatus(): Promise<AgentStatus> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<AgentStatus>('/api/agent/status')

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 400))
  return mockAgentStatus
}

export async function getAgents(): Promise<Agent[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<Agent[]>('/api/agent/list')

  await new Promise(resolve => setTimeout(resolve, 500))
  return mockAgents
}

export async function getAgentTasks(limit: number = 20): Promise<AgentTask[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<AgentTask[]>('/api/agent/tasks', { limit: limit.toString() })

  await new Promise(resolve => setTimeout(resolve, 450))
  return mockTasks.slice(0, limit)
}

export async function getAgentLogs(limit: number = 50): Promise<AgentLog[]> {
  // TODO: Replace with real API call when backend is ready
  // return api.get<AgentLog[]>('/api/agent/logs', { limit: limit.toString() })

  await new Promise(resolve => setTimeout(resolve, 350))
  return mockLogs.slice(0, limit)
}

export async function controlAgent(agentId: string, action: 'start' | 'stop' | 'restart'): Promise<void> {
  // TODO: Replace with real API call when backend is ready
  // return api.post('/api/agent/control', { agentId, action })

  // SAFETY: This is mock only - no real agent control occurs
  await new Promise(resolve => setTimeout(resolve, 800))
}
