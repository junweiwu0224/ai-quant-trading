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
  Network,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  WalletCards,
} from 'lucide-vue-next'

export type WorkflowGroup = '决策' | '行情' | '研究' | '策略与验证' | '组合与执行' | 'AI' | '报告与通知' | '系统'

export interface WorkflowEntry {
  id: string
  label: string
  description: string
  to: string
  group: WorkflowGroup
  icon: Component
  primary?: boolean
  mobile?: boolean
  command?: boolean
  readOnly?: boolean
}

/**
 * Canonical information architecture. Sidebar, mobile navigation, command
 * palette and the workflow index intentionally consume this same list.
 */
export const WORKFLOWS: WorkflowEntry[] = [
  { id: 'decision', label: '决策中心', description: '自选池、确定性动作、数据质量和推送资格', to: '/app/decision', group: '决策', icon: LayoutDashboard, primary: true, mobile: true, command: true },
  { id: 'intelligence', label: '市场情报', description: '广度、板块热力、热点、新闻和候选信号', to: '/app/intelligence', group: '行情', icon: ChartNoAxesCombined, primary: true, mobile: true, command: true },
  { id: 'research', label: '单股研究', description: 'K 线、技术指标、证据链和结构化研究', to: '/app/research', group: '研究', icon: Search, primary: true, mobile: true, command: true },
  { id: 'screener', label: '条件筛选', description: '条件构建、预设和候选池导入', to: '/app/research/screener', group: '研究', icon: ListFilter, primary: true, mobile: false, command: true },
  { id: 'alpha', label: 'Alpha 与因子', description: '预测、因子评价、Walk-Forward 和 SHAP', to: '/app/research/alpha', group: '研究', icon: Sparkles, primary: true, mobile: false, command: true },
  { id: 'formula', label: '公式与篮子', description: '公式目录、候选筛选和篮子回测计划', to: '/app/research/formula-basket', group: '研究', icon: SlidersHorizontal, primary: false, mobile: false, command: true },
  { id: 'validation', label: '验证与回测', description: '样本外验证、稳健性分析和资格检查', to: '/app/validation', group: '策略与验证', icon: FlaskConical, primary: true, mobile: true, command: true },
  { id: 'strategies', label: '策略工作台', description: '策略目录、代码、版本和组合回测', to: '/app/strategy', group: '策略与验证', icon: Code2, primary: true, mobile: false, command: true },
  { id: 'portfolio-risk', label: '组合与风控', description: '持仓、绩效、风险指标和模拟盘保护', to: '/app/portfolio-risk', group: '组合与执行', icon: Shield, primary: true, mobile: false, command: true },
  { id: 'portfolio', label: '持仓优化', description: '配置约束下的组合优化建议', to: '/app/portfolio', group: '组合与执行', icon: WalletCards, primary: false, mobile: false, command: true },
  { id: 'paper', label: '模拟盘', description: '订单、持仓、绩效和人工确认的纸面执行', to: '/app/paper', group: '组合与执行', icon: TrendingUp, primary: true, mobile: true, command: true },
  { id: 'conditional-orders', label: '条件单', description: '条件规则、执行审计和模拟盘边界', to: '/app/conditional-orders', group: '组合与执行', icon: GitBranch, primary: false, mobile: false, command: true },
  { id: 'ai', label: 'AI 工作台', description: 'Agent、研究任务、报告和 provider 状态', to: '/app/ai', group: 'AI', icon: Bot, primary: true, mobile: false, command: true },
  { id: 'ai-runtime', label: 'AI Runtime 配置', description: '模型、通道、能力矩阵和 token 使用', to: '/app/ai/runtime', group: 'AI', icon: Network, primary: false, mobile: false, command: true },
  { id: 'reports', label: '报告', description: '日报、决策报告、分享链接和投递记录', to: '/app/reports', group: '报告与通知', icon: FileText, primary: true, mobile: false, command: true, readOnly: true },
  { id: 'notifications', label: '通知路由', description: '目标、路由、测试和自动推送资格', to: '/app/notifications', group: '报告与通知', icon: Bell, primary: true, mobile: false, command: true },
  { id: 'alerts', label: '告警规则', description: '价格、涨跌、量能和触发历史', to: '/app/alerts', group: '报告与通知', icon: Megaphone, primary: false, mobile: false, command: true },
  { id: 'broker', label: 'Broker 安全', description: '脱敏能力状态和实盘禁用边界', to: '/app/broker', group: '系统', icon: FileCheck2, primary: false, mobile: false, command: true, readOnly: true },
  { id: 'settings', label: '设置', description: 'workspace、市场能力、Worker 和安全边界', to: '/app/settings', group: '系统', icon: Settings, primary: true, mobile: false, command: true },
]

export const WORKFLOW_GROUPS: WorkflowGroup[] = ['决策', '行情', '研究', '策略与验证', '组合与执行', 'AI', '报告与通知', '系统']
export const PRIMARY_WORKFLOWS = WORKFLOWS.filter((entry) => entry.primary)
export const MOBILE_WORKFLOWS = WORKFLOWS.filter((entry) => entry.mobile)
export const COMMAND_WORKFLOWS = WORKFLOWS.filter((entry) => entry.command)
