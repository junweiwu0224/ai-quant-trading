import type { Component } from 'vue'
import {
  Bell,
  Bot,
  ChartNoAxesCombined,
  Code2,
  FileCheck2,
  FileText,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  ListFilter,
  Megaphone,
  MoreHorizontal,
  Network,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  WalletCards,
} from 'lucide-vue-next'

export type WorkspaceId = 'decision' | 'research' | 'validation' | 'portfolio' | 'reports'
export type WorkflowGroup = '决策' | '行情' | '研究' | '策略与验证' | '组合与执行' | 'AI' | '报告与通知' | '系统'

export interface WorkflowEntry {
  id: string
  label: string
  description: string
  to: string
  group: WorkflowGroup
  icon: Component
  workspace?: WorkspaceId
  navLabel?: string
  primary?: boolean
  mobile?: boolean
  command?: boolean
  readOnly?: boolean
}

export interface WorkspaceTab {
  id: string
  label: string
  description: string
  to: string
  icon: Component
  preserveResearchContext?: boolean
}

export interface WorkspaceDefinition {
  id: WorkspaceId
  label: string
  description: string
  icon: Component
  tabs: WorkspaceTab[]
}

/**
 * Business workflows are grouped by the object users are working on. The
 * sidebar exposes only these stable workspaces; the local workspace nav owns
 * the capabilities inside each one.
 */
export const WORKFLOWS: WorkflowEntry[] = [
  { id: 'decision', label: '决策', description: '自选池、确定性动作、数据质量和推送资格', to: '/app/decision', group: '决策', icon: LayoutDashboard, workspace: 'decision', primary: true, mobile: true, command: true },
  { id: 'intelligence', label: '市场情报', description: '广度、板块热力、热点、新闻和候选信号', to: '/app/intelligence', group: '行情', icon: ChartNoAxesCombined, workspace: 'decision', command: true },
  { id: 'research', label: '研究', description: 'K 线、技术指标、证据链和结构化研究', to: '/app/research', group: '研究', icon: Search, workspace: 'research', primary: true, mobile: true, command: true },
  { id: 'screener', label: '条件筛选', description: '条件构建、预设和候选池导入', to: '/app/research/screener', group: '研究', icon: ListFilter, workspace: 'research', command: true },
  { id: 'alpha', label: 'Alpha 与因子', description: '预测、因子评价、Walk-Forward 和 SHAP', to: '/app/research/alpha', group: '研究', icon: Sparkles, workspace: 'research', command: true },
  { id: 'formula', label: '公式与篮子', description: '公式目录、候选筛选和篮子回测计划', to: '/app/research/formula-basket', group: '研究', icon: SlidersHorizontal, workspace: 'research', command: true },
  { id: 'validation', label: '验证', description: '样本外验证、稳健性分析和资格检查', to: '/app/validation', group: '策略与验证', icon: FlaskConical, workspace: 'validation', primary: true, mobile: true, command: true },
  { id: 'strategies', label: '策略工作台', description: '策略目录、代码、版本和组合回测', to: '/app/strategy', group: '策略与验证', icon: Code2, workspace: 'validation', command: true },
  { id: 'portfolio-risk', label: '组合与风控', navLabel: '组合', description: '持仓、绩效、风险指标和模拟盘保护', to: '/app/portfolio-risk', group: '组合与执行', icon: Shield, workspace: 'portfolio', primary: true, mobile: true, command: true },
  { id: 'portfolio', label: '持仓优化', description: '配置约束下的组合优化建议', to: '/app/portfolio', group: '组合与执行', icon: WalletCards, workspace: 'portfolio', command: true },
  { id: 'paper', label: '模拟盘', description: '订单、持仓、绩效和人工确认的纸面执行', to: '/app/paper', group: '组合与执行', icon: TrendingUp, workspace: 'portfolio', command: true },
  { id: 'conditional-orders', label: '条件单', description: '条件规则、执行审计和模拟盘边界', to: '/app/conditional-orders', group: '组合与执行', icon: GitBranch, workspace: 'portfolio', command: true },
  { id: 'ai', label: 'AI 工作台', description: 'Agent、研究任务、报告和 provider 状态', to: '/app/ai', group: 'AI', icon: Bot, workspace: 'research', command: true },
  { id: 'ai-runtime', label: 'AI Runtime 配置', description: '模型、通道、能力矩阵和 token 使用', to: '/app/ai/runtime', group: 'AI', icon: Network, workspace: 'research', command: true },
  { id: 'reports', label: '报告', navLabel: '报告', description: '日报、决策报告、分享链接和投递记录', to: '/app/reports', group: '报告与通知', icon: FileText, workspace: 'reports', primary: true, mobile: true, command: true, readOnly: true },
  { id: 'notifications', label: '通知路由', description: '目标、路由、测试和自动推送资格', to: '/app/notifications', group: '报告与通知', icon: Bell, workspace: 'reports', command: true },
  { id: 'alerts', label: '告警规则', description: '价格、涨跌、量能和触发历史', to: '/app/alerts', group: '报告与通知', icon: Megaphone, workspace: 'reports', command: true },
  { id: 'broker', label: 'Broker 安全', description: '脱敏能力状态和实盘禁用边界', to: '/app/broker', group: '系统', icon: FileCheck2, command: true, readOnly: true },
  { id: 'settings', label: '设置', description: 'workspace、市场能力、Worker 和安全边界', to: '/app/settings', group: '系统', icon: Settings, command: true },
  { id: 'more', label: '工作流地图', description: '查看全部工作区和模块索引', to: '/app/workflows', group: '系统', icon: MoreHorizontal, command: false },
]

export const WORKSPACE_DEFINITIONS: WorkspaceDefinition[] = [
  {
    id: 'decision',
    label: '决策',
    description: '从市场事实到确定性动作',
    icon: LayoutDashboard,
    tabs: [
      { id: 'decision', label: '今日决策', description: '查看当前结论、资格和下一步', to: '/app/decision', icon: LayoutDashboard },
      { id: 'intelligence', label: '市场情报', description: '广度、板块、热点和候选信号', to: '/app/intelligence', icon: ChartNoAxesCombined },
    ],
  },
  {
    id: 'research',
    label: '研究',
    description: '从候选、标的到证据和解释',
    icon: Search,
    tabs: [
      { id: 'research', label: '单股研究', description: 'K 线、指标、证据和风险', to: '/app/research', icon: Search, preserveResearchContext: true },
      { id: 'screener', label: '条件筛选', description: '构建条件并生成候选池', to: '/app/research/screener', icon: ListFilter },
      { id: 'alpha', label: 'Alpha 与因子', description: '模型、因子和 Walk-Forward', to: '/app/research/alpha', icon: Sparkles },
      { id: 'formula', label: '公式与篮子', description: '公式评估和篮子计划', to: '/app/research/formula-basket', icon: SlidersHorizontal },
      { id: 'ai', label: 'AI 研究', description: '冻结快照、研究任务和非权威 artifact', to: '/app/ai', icon: Bot },
    ],
  },
  {
    id: 'validation',
    label: '验证',
    description: '让策略结果可复现、可比较、可晋级',
    icon: FlaskConical,
    tabs: [
      { id: 'validation', label: '验证与回测', description: '回测、样本外、稳健性和资格', to: '/app/validation', icon: FlaskConical },
      { id: 'strategies', label: '策略工作台', description: '策略目录、版本和组合回测', to: '/app/strategy', icon: Code2 },
    ],
  },
  {
    id: 'portfolio',
    label: '组合',
    description: '持仓、风险和模拟执行',
    icon: Shield,
    tabs: [
      { id: 'portfolio-risk', label: '持仓与风控', description: '持仓、绩效和风险保护', to: '/app/portfolio-risk', icon: Shield },
      { id: 'portfolio', label: '持仓优化', description: '约束下的组合配置建议', to: '/app/portfolio', icon: WalletCards },
      { id: 'paper', label: '模拟盘', description: '纸面订单、持仓和绩效', to: '/app/paper', icon: TrendingUp },
      { id: 'conditional-orders', label: '条件单', description: '模拟盘条件规则和执行审计', to: '/app/conditional-orders', icon: GitBranch },
    ],
  },
  {
    id: 'reports',
    label: '报告',
    description: '结果、投递和自动化审计',
    icon: FileText,
    tabs: [
      { id: 'reports', label: '报告审计', description: '冻结输入、导出、分享和决策报告', to: '/app/reports', icon: FileText },
      { id: 'notifications', label: '通知路由', description: '目标、路由、测试和投递状态', to: '/app/notifications', icon: Bell },
      { id: 'alerts', label: '告警规则', description: '触发条件和历史记录', to: '/app/alerts', icon: Megaphone },
    ],
  },
]

export const WORKFLOW_GROUPS: WorkflowGroup[] = ['决策', '行情', '研究', '策略与验证', '组合与执行', 'AI', '报告与通知', '系统']
export const PRIMARY_WORKFLOWS = WORKFLOWS.filter((entry) => entry.primary)
export const MOBILE_WORKFLOWS = WORKFLOWS.filter((entry) => entry.mobile)
export const COMMAND_WORKFLOWS = WORKFLOWS.filter((entry) => entry.command)

export function workspaceForPath(path: string): WorkspaceDefinition | null {
  if (path === '/app/decision' || path === '/app/intelligence') return WORKSPACE_DEFINITIONS[0]
  if (path === '/app/research' || path.startsWith('/app/research/') || path === '/app/ai' || path.startsWith('/app/ai/')) return WORKSPACE_DEFINITIONS[1]
  if (path === '/app/validation' || path === '/app/strategy') return WORKSPACE_DEFINITIONS[2]
  if (path === '/app/portfolio-risk' || path === '/app/portfolio' || path === '/app/paper' || path === '/app/conditional-orders' || path === '/app/risk') return WORKSPACE_DEFINITIONS[3]
  if (path === '/app/reports' || path.startsWith('/app/reports/') || path === '/app/notifications' || path === '/app/alerts') return WORKSPACE_DEFINITIONS[4]
  return null
}
