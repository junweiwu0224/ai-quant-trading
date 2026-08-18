<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { ArrowRight, Database, FileText, LockKeyhole, Settings } from 'lucide-vue-next'
import MarketStatusCard from '../components/market/MarketStatusCard.vue'

const legacyToolKeys = [
  { key: 'paper', api: '/api/paper', route: '/app/paper', historicalPath: 'legacy-more-paper', capability: 'paper', mobile: true },
  { key: 'portfolio', api: '/api/portfolio', route: '/app/portfolio', historicalPath: 'legacy-more-portfolio', capability: 'portfolio', mobile: false },
  { key: 'risk', api: '/api/risk', route: '/app/risk', historicalPath: 'legacy-more-risk', capability: 'risk', mobile: false },
  { key: 'conditional-orders', api: '/api/conditional-orders', route: '/app/conditional-orders', historicalPath: 'legacy-more-conditional-orders', capability: 'conditional-orders', mobile: false },
  { key: 'alpha', api: '/api/alpha', route: '/app/research/alpha', historicalPath: 'legacy-more-alpha', capability: 'alpha', mobile: false },
  { key: 'strategy', api: '/api/strategy', route: '/app/strategy', historicalPath: 'legacy-more-strategy', capability: 'strategy', mobile: false },
  { key: 'agent-ops', api: '/api/ai', route: '/app/ai', historicalPath: 'legacy-more-agent-ops', capability: 'ai', mobile: false },
  { key: 'ai-runtime', api: '/api/ai', route: '/app/ai/runtime', historicalPath: 'legacy-more-ai-runtime', capability: 'ai-runtime', mobile: false },
  { key: 'screener', api: '/api/screener', route: '/app/research/screener', historicalPath: 'legacy-more-screener', capability: 'screener', mobile: false },
  { key: 'portfolio-risk', api: '/api/portfolio', route: '/app/portfolio-risk', historicalPath: 'legacy-more-portfolio-risk', capability: 'portfolio-risk', mobile: false },
  { key: 'strategies-backtest', api: '/api/backtest', route: '/app/strategy', historicalPath: 'legacy-more-strategies-backtest', capability: 'strategy', mobile: false },
  { key: 'alpha-factors', api: '/api/alpha', route: '/app/research/alpha', historicalPath: 'legacy-more-alpha-factors', capability: 'alpha', mobile: false },
  { key: 'formula-basket', api: '/api/alpha', route: '/app/research/formula-basket', historicalPath: 'legacy-more-formula-basket', capability: 'formula', mobile: false },
  { key: 'agents', api: '/api/ai', route: '/app/ai', historicalPath: 'legacy-more-agents', capability: 'ai', mobile: false },
  { key: 'broker-live', api: '/api/broker', route: '/app/broker', historicalPath: 'legacy-more-broker-live', capability: 'disabled', mobile: false },
]

const directory = [
  { key: 'reports', title: '报告索引', description: '查看冻结报告、来源、分享和投递记录。', route: '/app/reports', icon: FileText },
  { key: 'notifications', title: '通知与投递', description: '管理通知目标、路由和失败状态。', route: '/app/notifications', icon: Database },
  { key: 'settings', title: '工作区设置', description: '查看 Worker readiness、市场能力和安全边界。', route: '/app/settings', icon: Settings },
  { key: 'broker-live', title: 'Broker 与实盘状态', description: '只读查看脱敏状态；真实下单、撤单和凭证写入保持禁用。', route: '/app/broker', icon: LockKeyhole },
]
</script>

<template>
  <section class="directory-page">
    <div class="page-head">
      <div>
        <span class="eyebrow">系统目录</span>
        <h1>工作区工具目录</h1>
        <p>高频研究、验证、组合和模拟盘操作已放在主导航；这里保留低频系统入口和兼容链接。</p>
      </div>
    </div>

    <section class="panel">
      <div class="panel-head"><div><h2>系统入口</h2><p>不会在此页隐藏研究或交易主流程。</p></div><span class="tag">{{ directory.length }} 个入口</span></div>
      <div class="panel-body directory-grid">
        <RouterLink v-for="item in directory" :key="item.route" :to="item.route" class="directory-card">
          <span class="directory-icon"><component :is="item.icon" :size="20" /></span>
          <span class="directory-copy"><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span>
          <ArrowRight :size="17" class="directory-arrow" />
        </RouterLink>
      </div>
    </section>

    <section class="panel market-panel">
      <div class="panel-head"><div><h2>六市场能力</h2><p>状态由 canonical market adapter 和运行时来源共同决定。</p></div></div>
      <div class="panel-body"><MarketStatusCard /></div>
    </section>
  </section>
</template>

<style scoped>
.directory-page { display: grid; gap: 18px; }
.eyebrow { color: var(--color-accent); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.page-head h1 { margin-top: 6px; }
.directory-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.directory-card { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md); color: inherit; text-decoration: none; transition: transform .18s ease, border-color .18s ease, background .18s ease; }
.directory-card:hover { transform: translateY(-2px); border-color: var(--color-accent); background: var(--color-bg-tertiary); }
.directory-icon { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 10px; background: var(--color-accent-bg); color: var(--color-accent); }
.directory-copy { min-width: 0; display: grid; gap: 4px; }
.directory-copy strong { color: var(--color-text-primary); }
.directory-copy small { color: var(--color-text-secondary); line-height: 1.5; }
.directory-arrow { color: var(--color-text-tertiary); transition: transform .18s ease; }
.directory-card:hover .directory-arrow { transform: translateX(3px); color: var(--color-accent); }
.market-panel { margin-top: 0; }
@media (max-width: 767px) { .directory-grid { grid-template-columns: 1fr; } }
</style>
