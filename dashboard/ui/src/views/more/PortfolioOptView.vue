<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, BarChart3, Play, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import AsyncState from '../../components/base/AsyncState.vue'
import { getPortfolioMethods, optimizePortfolio, type PortfolioOptimizationMethod, type PortfolioOptimizationResult } from '../../api/portfolio'
import { useAppStore } from '../../stores/app'

const app = useAppStore()
const methods = ref<PortfolioOptimizationMethod[]>([])
const result = ref<PortfolioOptimizationResult | null>(null)
const loading = ref(false)
const error = ref('')
const form = ref({
  codes: '',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  method: 'max_sharpe',
  risk_free: 0.03,
})

const codes = computed(() => [...new Set(form.value.codes.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean))])
const weightEntries = computed(() => Object.entries(result.value?.weights || {})
  .map(([code, weight]) => ({ code, weight: Number(weight) }))
  .filter((item) => Number.isFinite(item.weight))
  .sort((left, right) => right.weight - left.weight))
const methodLabel = computed(() => methods.value.find((item) => item.name === result.value?.method)?.label || result.value?.method || '—')

function number(value: unknown, digits = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })
}

function percent(value: unknown, digits = 2) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })}%`
}

async function loadMethods() {
  error.value = ''
  try {
    methods.value = await getPortfolioMethods()
    if (!methods.value.some((item) => item.name === form.value.method) && methods.value[0]) form.value.method = methods.value[0].name
    if (!form.value.codes && app.watchlist.length) form.value.codes = app.watchlist.map((item) => item.code).slice(0, 20).join(',')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '组合优化方法加载失败'
  }
}

async function runOptimization() {
  if (codes.value.length < 2) {
    error.value = '至少输入 2 只股票代码'
    return
  }
  if (codes.value.length > 20) {
    error.value = '单次最多优化 20 只股票'
    return
  }
  if (form.value.start_date > form.value.end_date) {
    error.value = '开始日期不能晚于结束日期'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await optimizePortfolio({ ...form.value, codes: codes.value })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '组合优化失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadMethods)
</script>

<template>
  <section class="portfolio-opt-view">
    <div class="page-head">
      <div><RouterLink class="muted small portfolio-opt-back" to="/app/portfolio-risk"><ArrowLeft :size="14" />组合工作区</RouterLink><h1>持仓优化</h1><p>基于真实历史收益率运行等权、风险平价、最小方差或最大夏普研究；结果不会自动调仓或创建订单。</p></div>
      <button class="button" type="button" :disabled="loading" @click="loadMethods"><RefreshCw :size="16" />刷新方法</button>
    </div>

    <AsyncState v-if="error" state="error" :message="error" @retry="loadMethods" />

    <section class="panel portfolio-opt-form">
      <div class="panel-head"><div><h2>优化输入</h2><p>股票代码、时间范围、方法与无风险利率会原样提交到 `/api/portfolio-opt/optimize`。</p></div><span class="tag warn">研究操作</span></div>
      <div class="panel-body">
        <div class="field-grid">
          <div class="field portfolio-opt-codes"><label for="portfolio-opt-codes">股票代码</label><input id="portfolio-opt-codes" v-model="form.codes" placeholder="600519,000001；2–20 只" /></div>
          <div class="field"><label for="portfolio-opt-method">优化方法</label><select id="portfolio-opt-method" v-model="form.method" class="field-select"><option v-for="method in methods" :key="method.name" :value="method.name">{{ method.label }}</option></select></div>
          <div class="field"><label for="portfolio-opt-start">开始日期</label><input id="portfolio-opt-start" v-model="form.start_date" type="date" /></div>
          <div class="field"><label for="portfolio-opt-end">结束日期</label><input id="portfolio-opt-end" v-model="form.end_date" type="date" /></div>
          <div class="field"><label for="portfolio-opt-risk-free">无风险利率</label><input id="portfolio-opt-risk-free" v-model.number="form.risk_free" type="number" min="0" max="1" step="0.001" /></div>
        </div>
        <div v-if="methods.length" class="portfolio-methods"><span v-for="method in methods" :key="method.name" :class="{ active: form.method === method.name }"><strong>{{ method.label }}</strong>{{ method.description }}</span></div>
        <div class="security-note"><ShieldCheck :size="16" /><span>优化结果只用于人工研究，不修改持仓、不改变自动推送资格，也不会进入 Broker 或模拟盘订单。</span></div>
        <div class="form-actions"><button class="button primary" type="button" :disabled="loading || methods.length === 0" @click="runOptimization"><Play :size="15" />{{ loading ? '优化中' : '运行优化' }}</button><span class="muted small">当前 {{ codes.length }} 只股票</span></div>
      </div>
    </section>

    <template v-if="result">
      <div class="portfolio-opt-summary" aria-label="优化结果摘要">
        <div><span>方法</span><strong>{{ methodLabel }}</strong></div>
        <div><span>预期年化收益</span><strong>{{ percent(result.expected_return) }}</strong></div>
        <div><span>预期年化波动</span><strong>{{ percent(result.expected_volatility) }}</strong></div>
        <div><span>夏普比率</span><strong>{{ number(result.sharpe_ratio) }}</strong></div>
      </div>

      <section class="panel">
        <div class="panel-head"><div><h2>建议权重</h2><p>权重来自当前 API 响应；没有足够历史数据时保持空状态，不回退到演示数据。</p></div><BarChart3 :size="18" class="faint" /></div>
        <div v-if="!weightEntries.length" class="panel-body"><div class="empty"><strong>没有可用权重</strong><span>当前代码范围可能缺少至少 30 个共同交易日的本地历史数据。</span></div></div>
        <div v-else class="portfolio-weight-list">
          <div v-for="item in weightEntries" :key="item.code" class="portfolio-weight-row"><div><strong>{{ item.code }}</strong><span>{{ percent(item.weight) }}</span></div><div class="portfolio-weight-track"><i :style="{ width: `${Math.max(0, Math.min(100, item.weight * 100))}%` }" /></div></div>
        </div>
      </section>
    </template>

    <div v-else-if="!loading" class="empty portfolio-opt-empty"><strong>等待显式运行</strong><span>页面不会显示虚构持仓、风险指标或优化建议。</span></div>
  </section>
</template>

<style scoped>
.portfolio-opt-back { display:inline-flex; align-items:center; gap:5px; margin-bottom:9px; }
.portfolio-opt-form { margin-bottom:18px; }
.portfolio-opt-codes { grid-column:span 2; }
.portfolio-methods { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:8px; margin-top:15px; }
.portfolio-methods span { min-width:0; padding:10px; border:1px solid var(--color-line); border-radius:var(--radius-md); color:var(--color-ink-soft); font-size:11px; line-height:1.45; }
.portfolio-methods span.active { border-color:var(--color-accent); background:var(--color-accent-pale); color:var(--color-accent-strong); }
.portfolio-methods strong { display:block; margin-bottom:3px; color:var(--color-ink); font-size:12px; }
.portfolio-opt-summary { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); margin-bottom:18px; border:1px solid var(--color-line); background:var(--color-surface); }
.portfolio-opt-summary > div { display:grid; gap:5px; min-width:0; padding:14px 16px; border-right:1px solid var(--color-line); }
.portfolio-opt-summary > div:last-child { border-right:0; }
.portfolio-opt-summary span { color:var(--color-ink-soft); font-size:12px; }
.portfolio-opt-summary strong { overflow:hidden; font:600 15px/1.2 var(--font-family-mono); text-overflow:ellipsis; white-space:nowrap; }
.portfolio-weight-list { display:grid; padding:7px 18px 14px; }
.portfolio-weight-row { display:grid; grid-template-columns:150px minmax(0, 1fr); align-items:center; gap:16px; padding:11px 0; border-bottom:1px solid var(--color-line); }
.portfolio-weight-row:last-child { border-bottom:0; }
.portfolio-weight-row > div:first-child { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.portfolio-weight-row strong { font-family:var(--font-family-mono); font-size:12px; }
.portfolio-weight-row span { color:var(--color-ink-soft); font-size:11px; }
.portfolio-weight-track { height:8px; overflow:hidden; border-radius:4px; background:var(--color-surface-strong); }
.portfolio-weight-track i { display:block; height:100%; border-radius:inherit; background:var(--color-accent); }
.portfolio-opt-empty { margin-top:18px; }
@media (max-width:900px) { .portfolio-methods { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width:767px) {
  .portfolio-opt-codes { grid-column:auto; }
  .portfolio-opt-summary { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .portfolio-opt-summary > div:nth-child(2n) { border-right:0; }
  .portfolio-opt-summary > div { border-bottom:1px solid var(--color-line); }
  .portfolio-opt-summary > div:nth-last-child(-n + 2) { border-bottom:0; }
  .portfolio-weight-row { grid-template-columns:1fr; gap:7px; }
}
@media (max-width:430px) {
  .portfolio-methods, .portfolio-opt-summary { grid-template-columns:1fr; }
  .portfolio-opt-summary > div { border-right:0; border-bottom:1px solid var(--color-line); }
  .portfolio-opt-summary > div:nth-last-child(-n + 2) { border-bottom:1px solid var(--color-line); }
  .portfolio-opt-summary > div:last-child { border-bottom:0; }
}
</style>
