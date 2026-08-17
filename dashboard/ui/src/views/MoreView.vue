<script setup lang="ts">
import { ArrowLeft, Layers3, TrendingUp, PieChart, Shield, GitBranch, Sparkles, Code2, Bot, Settings } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import MarketStatusCard from '../components/market/MarketStatusCard.vue'
import BaseCard from '../components/base/BaseCard.vue'

type SubPage = {
  key: string
  name: string
  description: string
  route: string
  icon: any
  status: 'migration' | 'active'
}

type Tool = {
  key: string
  name: string
  description: string
  group: string
  api?: string
  route: string
  historicalPath: string
  status: 'native-readonly' | 'native-workflow'
  capability: 'read-only' | 'manual-confirmation' | 'disabled'
  mobile: 'responsive' | 'wide-workspace'
}

const subPages: SubPage[] = [
  { key: 'paper', name: '模拟盘交易', description: '完整的模拟交易环境，用于验证策略和训练交易技能', route: '/app/more/paper', icon: TrendingUp, status: 'migration' },
  { key: 'portfolio', name: '持仓优化', description: '基于现代投资组合理论的持仓分析与优化建议', route: '/app/more/portfolio', icon: PieChart, status: 'migration' },
  { key: 'risk', name: '风险监控', description: '实时风险指标监控与预警系统', route: '/app/more/risk', icon: Shield, status: 'migration' },
  { key: 'conditional-orders', name: '条件单', description: '智能条件单设置与执行监控', route: '/app/more/conditional-orders', icon: GitBranch, status: 'migration' },
  { key: 'alpha', name: 'Alpha 因子', description: '因子研究、回测与组合优化平台', route: '/app/more/alpha', icon: Sparkles, status: 'migration' },
  { key: 'strategy', name: '策略工作台', description: '策略开发、回测与版本管理的集成环境', route: '/app/more/strategy', icon: Code2, status: 'migration' },
  { key: 'agent-ops', name: 'Agent 运维', description: 'AI Agent 监控、任务管理与运维工具', route: '/app/more/agent-ops', icon: Bot, status: 'migration' },
  { key: 'ai-runtime', name: 'AI Runtime 配置', description: 'AI 模型、Provider 与 Token 使用管理', route: '/app/more/ai-runtime', icon: Settings, status: 'migration' },
]

const tools: Tool[] = [
  { key: 'market-radar', name: '市场雷达与机会池', description: '在决策中心读取市场雷达、自选池和数据健康，统一显示来源和当前状态。', group: '行情', api: '/api/market/radar?fast=true', route: '/app/decision', historicalPath: '/#overview', status: 'native-workflow', capability: 'read-only', mobile: 'responsive' },
  { key: 'intelligence', name: '市场情报工作台', description: '恢复市场广度、板块热力、热点归因、新闻、AI 信号和问财研究入口；每个结果都保留来源和可用性。', group: '行情', api: '/api/market/breadth', route: '/app/intelligence', historicalPath: '/#intelligence', status: 'native-workflow', capability: 'read-only', mobile: 'responsive' },
  { key: 'watchlists-alerts', name: '自选股与告警', description: '决策中心管理 workspace 自选股；告警规则在独立页面完成创建、编辑、启停和删除。', group: '行情', api: '/api/alerts/rules', route: '/app/more/alerts', historicalPath: '/#alerts', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'responsive' },
  { key: 'alerts', name: '告警规则', description: '完整维护价格、涨跌、量能和换手告警，触发历史与外部投递状态分开显示。', group: '交易安全', api: '/api/alerts/rules', route: '/app/more/alerts', historicalPath: '/#alerts', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'responsive' },
  { key: 'conditional-orders', name: '条件单', description: '查看并维护条件单规则和执行审计；新规则默认关闭，任何订单动作仍要求人工确认并受模拟盘边界保护。', group: '交易安全', api: '/api/conditional-orders/rules', route: '/app/more/conditional-orders', historicalPath: '/#alerts', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'responsive' },
  { key: 'screener', name: '条件筛选与 AI 选股', description: '使用筛选字段、预设和候选池来源生成候选结果；候选结果不能直接变成确定性动作。', group: '研究', api: '/api/screener/presets', route: '/app/more/screener', historicalPath: '/#screener', status: 'native-workflow', capability: 'read-only', mobile: 'wide-workspace' },
  { key: 'stock-detail', name: '单股研究输入', description: '在单股研究中使用 K 线、指标、证据、比较和画线；真实数据缺失时保持手动研究边界。', group: '研究', route: '/app/research/CN/600519', historicalPath: '/#stock-detail?code=600519', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'portfolio-risk', name: '持仓、绩效与风控', description: '读取持仓快照、风险指标、行业分布并提供明确确认的模拟盘平仓、止损止盈和导出操作。', group: '组合', api: '/api/portfolio/snapshot', route: '/app/more/portfolio-risk', historicalPath: '/#portfolio', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'strategies-backtest', name: '策略、版本与回测', description: '在策略工作台运行 CRUD、代码校验、版本、优化、ensemble 和历史记录，验证页继续负责策略资格。', group: '验证', api: '/api/strategy/list', route: '/app/more/strategies', historicalPath: '/#strategy-admin', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'validation', name: '策略验证与回测', description: '运行单股回测、滚动验证和组合分析；结果只用于验证，不会自动改写策略或创建订单。', group: '验证', api: '/api/backtest/run', route: '/app/validation', historicalPath: '/#backtest', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'alpha-factors', name: 'Alpha、因子与 Walk-Forward', description: '在 Alpha 工作区运行预测、因子评价、SHAP、Walk-Forward、模型比较和相关性分析；候选晋级仍需显式研究操作。', group: '研究', api: '/api/alpha/model-status', route: '/app/more/alpha-factors', historicalPath: '/#alpha', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'formula-basket', name: '公式系统与篮子计划', description: '在 Alpha 工作区使用公式目录、候选筛选、篮子分配计划和篮子回测；计划不会绕过验证或创建真实订单。', group: '研究', api: '/api/alpha/formula/catalog', route: '/app/more/formula-basket', historicalPath: '/#alpha', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'wide-workspace' },
  { key: 'paper', name: '模拟盘与风控执行', description: '完整查看模拟盘状态、订单、持仓、绩效和风控，并以明确确认执行模拟盘写操作；实盘入口显式禁用。', group: '模拟', api: '/api/paper/positions', route: '/app/more/paper', historicalPath: '/#paper', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'responsive' },
  { key: 'agents', name: 'AI Runtime 与 Agent 工作台', description: '统一使用 AI Runtime 管理会话、技能、研究任务、报告和 provider；AI 输出不会写入确定性动作。', group: '高级', api: '/api/ai/status', route: '/app/more/agents', historicalPath: '/#agent', status: 'native-workflow', capability: 'manual-confirmation', mobile: 'responsive' },
  { key: 'daily-briefs', name: '研究日报与报告', description: '在报告页查看日报、决策报告、来源和投递状态；完整报告走独立只读链接。', group: '高级', api: '/api/agentic/briefs/daily', route: '/app/reports', historicalPath: '/#reports', status: 'native-readonly', capability: 'read-only', mobile: 'responsive' },
  { key: 'broker-live', name: 'Broker 与实盘设置', description: '查看脱敏能力状态；当前阶段明确禁用真实下单、撤单、权限变更和凭证写入。', group: '安全', api: '/api/broker', route: '/app/more/broker-live', historicalPath: '/#settings', status: 'native-readonly', capability: 'disabled', mobile: 'responsive' },
]

const statusLabels: Record<Tool['status'], string> = {
  'native-readonly': '原生 Vue 只读工作流',
  'native-workflow': '原生 Vue 工作流',
}

const capabilityLabels: Record<Tool['capability'], string> = {
  'read-only': '只读',
  'manual-confirmation': '需人工确认',
  disabled: '显式禁用',
}

const mobileLabels: Record<Tool['mobile'], string> = {
  responsive: '移动端自适应',
  'wide-workspace': '移动端横向数据区',
}
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>更多工具</h1>
        <p>高级能力通过明确的 Vue 工作流进入工作台；每项能力都显示来源、移动端形态和安全边界。</p>
      </div>
      <Layers3 :size="22" class="faint" />
    </div>

    <section class="panel">
      <div class="panel-head">
        <div><h2>高级功能模块</h2><p>专业交易与研究工具的快速访问入口。</p></div>
        <span class="tag good">{{ subPages.length }} 个模块</span>
      </div>
      <div class="panel-body">
        <div class="subpage-grid">
          <RouterLink v-for="page in subPages" :key="page.key" :to="page.route" class="subpage-card-link">
            <BaseCard hoverable padding="lg">
              <div class="subpage-card">
                <div class="subpage-icon">
                  <component :is="page.icon" :size="24" />
                </div>
                <div class="subpage-content">
                  <div class="subpage-header">
                    <h3>{{ page.name }}</h3>
                    <span v-if="page.status === 'migration'" class="status-badge migration">迁移中</span>
                  </div>
                  <p>{{ page.description }}</p>
                </div>
                <div class="subpage-arrow">
                  <ArrowLeft :size="16" style="transform:rotate(180deg)" />
                </div>
              </div>
            </BaseCard>
          </RouterLink>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:18px">
      <div class="panel-head">
        <div><h2>功能覆盖矩阵</h2><p>每项能力都直达一个可用的 Vue 工作流，并保留接口映射、桌面/移动状态和明确的读写安全说明。</p></div>
        <span class="tag good">{{ tools.length }} 个 Vue 工作流</span>
      </div>
      <div class="panel-body">
        <div class="tool-grid">
          <article v-for="tool in tools" :key="tool.key" class="tool-card">
            <span class="tag">{{ tool.group }}</span>
            <strong style="margin-top:10px">{{ tool.name }}</strong>
            <p>{{ tool.description }}</p>
            <div class="data-source">
              <span>{{ statusLabels[tool.status] }}</span>
              <span>{{ capabilityLabels[tool.capability] }}</span>
              <span>{{ mobileLabels[tool.mobile] }}</span>
            </div>
            <div class="report-meta">
              <span v-if="tool.api">API: {{ tool.api }}</span>
              <span>历史路径映射: {{ tool.historicalPath }}</span>
            </div>
            <div class="form-actions">
              <RouterLink class="button primary" :to="tool.route">打开 Vue 工作流 <ArrowLeft :size="14" style="transform:rotate(180deg)" /></RouterLink>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><h2>全球市场数据能力</h2><p>六市场框架状态与数据能力概览。</p></div></div>
      <div class="panel-body">
        <MarketStatusCard />
      </div>
    </section>

    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><h2>迁移与回滚规则</h2><p>新页面先保证状态可见和安全边界，再逐步替换深度操作面板。</p></div></div>
      <div class="panel-body"><div class="data-source"><span>历史 query/hash 仍能还原股票和来源上下文</span><span>未配置 Broker 时显式禁用</span><span>外部写操作不由此页面隐式触发</span><span>确定性决策不接受 AI 改写</span></div></div>
    </section>
  </section>
</template>

<style scoped>
.subpage-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.subpage-card-link {
  text-decoration: none;
  color: inherit;
}

.subpage-card {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-lg);
  min-height: 100px;
}

.subpage-icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-accent-pale);
  color: var(--color-accent);
  border-radius: var(--radius-lg);
}

.subpage-content {
  flex: 1;
  min-width: 0;
}

.subpage-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
  flex-wrap: wrap;
}

.subpage-header h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

.subpage-content p {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  line-height: var(--line-height-relaxed);
  margin: 0;
}

.subpage-arrow {
  flex-shrink: 0;
  color: var(--color-ink-faint);
  opacity: 0;
  transition: all var(--duration-normal) var(--ease-smooth);
}

.subpage-card-link:hover .subpage-arrow {
  opacity: 1;
  transform: translateX(4px);
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.status-badge.migration {
  background-color: var(--color-warn-bg);
  color: var(--color-warn);
  border: 1px solid var(--color-warn);
}

@media (max-width: 768px) {
  .subpage-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-md);
  }

  .subpage-card {
    gap: var(--spacing-md);
  }

  .subpage-icon {
    width: 40px;
    height: 40px;
  }

  .subpage-header h3 {
    font-size: var(--font-size-base);
  }
}
</style>
