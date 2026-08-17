<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, BarChart3, CircleAlert, Clock3, Database, ExternalLink, Newspaper, RefreshCw, Search, Sparkles } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'

type Row = Record<string, any>

const breadth = ref<Row | null>(null)
const sectors = ref<Row[]>([])
const heatmap = ref<Row[]>([])
const hotspots = ref<Row[]>([])
const news = ref<Row[]>([])
const signals = ref<Row[]>([])
const query = ref('')
const queryResult = ref<Row | null>(null)
const loading = ref(false)
const queryLoading = ref(false)
const message = ref('')

function list(payload: any, keys: string[]) {
  if (Array.isArray(payload)) return payload
  for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key]
  return []
}

function number(value: unknown, digits = 0) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function percent(value: unknown) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return `${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false })}%`
}

function changeClass(value: unknown) {
  const numberValue = Number(value)
  return numberValue > 0 ? 'good' : numberValue < 0 ? 'bad' : 'muted'
}

function heatColor(value: unknown) {
  const numberValue = Math.max(-5, Math.min(5, Number(value) || 0))
  const intensity = Math.abs(numberValue) / 5
  if (numberValue > 0) return `color-mix(in srgb, var(--up) ${Math.round(18 + intensity * 42)}%, var(--surface))`
  if (numberValue < 0) return `color-mix(in srgb, var(--down) ${Math.round(18 + intensity * 42)}%, var(--surface))`
  return 'var(--surface-muted)'
}

const breadthTotal = computed(() => Number(breadth.value?.total_stocks || breadth.value?.total || 0))
const breadthLabel = computed(() => {
  const up = Number(breadth.value?.up_count || 0)
  const down = Number(breadth.value?.down_count || 0)
  if (!breadth.value) return '等待数据'
  if (up > down * 1.2) return '偏强'
  if (down > up * 1.2) return '偏弱'
  return '分化'
})

async function load() {
  loading.value = true
  message.value = ''
  const results = await Promise.allSettled([
    api.marketBreadth(), api.marketSectors(true), api.marketHeatmap(true), api.marketHotspot(), api.marketNews(), api.signalTop(20),
  ])
  const value = <T>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
  breadth.value = value<Row>(0)
  const sectorResponse = value<Row>(1)
  const heatmapResponse = value<Row>(2)
  const hotspotResponse = value<Row>(3)
  const newsResponse = value<Row>(4)
  const signalResponse = value<Row>(5)
  sectors.value = list(sectorResponse, ['sectors', 'items'])
  heatmap.value = list(heatmapResponse, ['sectors', 'items'])
  hotspots.value = list(hotspotResponse, ['hotspots', 'concepts', 'sectors', 'items']).slice(0, 12)
  news.value = list(newsResponse, ['news', 'items', 'articles']).slice(0, 16)
  signals.value = list(signalResponse, ['items', 'signals', 'data']).slice(0, 20)
  if (results.every((item) => item.status === 'rejected')) message.value = '情报数据暂不可用；页面保留空状态，不用默认值伪造市场判断。'
  else if (results.some((item) => item.status === 'rejected')) message.value = '部分情报源暂不可用；每个区块会保留自己的来源和空状态。'
  loading.value = false
}

async function runIwencai() {
  if (!query.value.trim()) return
  queryLoading.value = true
  message.value = ''
  try {
    queryResult.value = await api.iwencai(query.value.trim())
  } catch (error) {
    message.value = error instanceof Error ? error.message : '问财查询失败'
  } finally {
    queryLoading.value = false
  }
}

function itemCode(item: Row) {
  return item.code || item.symbol || item.stock_code || ''
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><h1>市场情报</h1><p>把市场广度、板块轮动、新闻和信号放在同一张研究桌上。每个区块都显示来源、覆盖和是否可能过期。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ spin: loading }" />刷新情报</button></div>
    <div v-if="message" class="error-box" role="status"><CircleAlert :size="16" />{{ message }}</div>

    <div class="summary-strip intelligence-summary"><div class="summary-item"><span>市场状态</span><strong>{{ breadthLabel }}</strong><small>基于 {{ breadthTotal ? number(breadthTotal) : '—' }} 个覆盖标的</small></div><div class="summary-item"><span>上涨家数</span><strong class="good">{{ number(breadth?.up_count) }}</strong><small>涨停 {{ number(breadth?.limit_up) }}</small></div><div class="summary-item"><span>下跌家数</span><strong class="bad">{{ number(breadth?.down_count) }}</strong><small>跌停 {{ number(breadth?.limit_down) }}</small></div><div class="summary-item"><span>信号候选</span><strong>{{ signals.length || '—' }}</strong><small>当前返回范围，不代表已验证</small></div></div>

    <div class="section-grid two intelligence-top-grid">
      <section class="panel"><div class="panel-head"><div><h2>市场广度</h2><p>本地覆盖池的涨跌统计；不把不可用数据替换成 0。</p></div><Activity :size="18" class="faint" /></div><div class="panel-body"><div class="breadth-bars"><div><span>上涨</span><i :style="{ width: `${Math.min(100, Number(breadth?.up_count || 0) / Math.max(1, breadthTotal) * 100)}%` }" class="bar-up" /><strong>{{ number(breadth?.up_count) }}</strong></div><div><span>下跌</span><i :style="{ width: `${Math.min(100, Number(breadth?.down_count || 0) / Math.max(1, breadthTotal) * 100)}%` }" class="bar-down" /><strong>{{ number(breadth?.down_count) }}</strong></div><div><span>平盘</span><i :style="{ width: `${Math.min(100, Number(breadth?.flat_count || 0) / Math.max(1, breadthTotal) * 100)}%` }" class="bar-flat" /><strong>{{ number(breadth?.flat_count) }}</strong></div></div><div class="data-source" style="margin-top:16px"><span><Database :size="14" />{{ breadth?.source || '—' }}</span><span><Clock3 :size="14" />{{ breadth?.generated_at || '—' }}</span><span class="tag" :class="breadth?.stale ? 'warn' : 'good'">{{ breadth?.stale ? '可能过期' : breadth ? '已读取' : '等待' }}</span></div></div></section>
      <section class="panel"><div class="panel-head"><div><h2>问财检索</h2><p>自然语言结果是研究候选，需回到单股研究和验证工作流。</p></div><Search :size="18" class="faint" /></div><div class="panel-body"><div class="inline-search"><input v-model="query" aria-label="问财自然语言查询" placeholder="例如：PE 低于 20 且 ROE 大于 15%" @keydown.enter.prevent="runIwencai" /><button class="button primary" type="button" :disabled="queryLoading || !query.trim()" @click="runIwencai"><Search :size="15" />{{ queryLoading ? '查询中' : '查询' }}</button></div><div v-if="!queryResult" class="empty compact-empty">输入条件开始查询。</div><pre v-else class="result-code compact-result">{{ JSON.stringify(queryResult, null, 2) }}</pre></div></section>
    </div>

    <div class="section-grid two intelligence-main-grid">
      <section class="panel"><div class="panel-head"><div><h2>板块热力与轮动</h2><p>色块同时显示涨跌数值；来源不可用时不会伪造排名。</p></div><BarChart3 :size="18" class="faint" /></div><div class="panel-body"><div v-if="!heatmap.length && !sectors.length" class="empty">暂无板块数据。</div><div v-else class="heatmap-grid"><RouterLink v-for="item in heatmap.slice(0, 30)" :key="item.code || item.name" class="heat-cell" :style="{ background: heatColor(item.change_pct) }" :to="item.leader_code ? `/app/research/CN/${encodeURIComponent(String(item.leader_code))}` : '/app/research'"><strong>{{ item.name || '—' }}</strong><span :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</span><small>涨 {{ number(item.up_count) }} · 跌 {{ number(item.down_count) }}</small></RouterLink></div><div v-if="sectors.length" class="table-scroll" style="margin-top:18px"><table class="decision-table"><thead><tr><th>板块</th><th>涨跌</th><th>涨/跌</th><th>领涨</th></tr></thead><tbody><tr v-for="item in sectors.slice(0, 12)" :key="`sector-${item.code || item.name}`"><td><strong>{{ item.name || '—' }}</strong></td><td :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</td><td>{{ number(item.up_count) }} / {{ number(item.down_count) }}</td><td>{{ item.leader || '—' }}</td></tr></tbody></table></div></div></section>
      <div class="stack-lg">
        <section class="panel"><div class="panel-head"><div><h2>热点归因</h2><p>热点是研究线索，不是确定性动作。</p></div><Sparkles :size="18" class="faint" /></div><div class="panel-body"><div v-if="!hotspots.length" class="empty">暂无可验证热点。</div><div v-else class="intel-list"><div v-for="(item, index) in hotspots" :key="String(item.id || item.name || index)" class="intel-list-row"><span class="rank-number">{{ index + 1 }}</span><div><strong>{{ item.name || item.title || item.concept || '热点' }}</strong><small>{{ item.reason || item.description || item.leader || '—' }}</small></div><span class="tag" :class="changeClass(item.change_pct)">{{ percent(item.change_pct) }}</span></div></div></div></section>
        <section class="panel"><div class="panel-head"><div><h2>市场新闻</h2><p>新闻用于情报核验，查看原文前保持来源可见。</p></div><Newspaper :size="18" class="faint" /></div><div class="panel-body"><div v-if="!news.length" class="empty">暂无市场新闻。</div><div v-else class="news-list"><article v-for="(item, index) in news" :key="String(item.id || item.url || index)" class="news-row"><div><strong>{{ item.title || item.name || '未命名新闻' }}</strong><small>{{ item.source || item.publisher || '来源未返回' }} · {{ item.published_at || item.time || item.created_at || '—' }}</small></div><a v-if="item.url || item.link" :href="item.url || item.link" target="_blank" rel="noopener noreferrer" class="icon-button compact-icon" title="打开原文" aria-label="打开新闻原文"><ExternalLink :size="14" /></a></article></div></div></section>
      </div>
    </div>

    <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>AI 信号池</h2><p>候选信号保留质量和验证语义；未验证信号不会自动进入决策或推送资格。</p></div><Sparkles :size="18" class="faint" /></div><div class="panel-body"><div v-if="!signals.length" class="empty">暂无信号候选。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>标的</th><th>分数</th><th>验证</th><th>来源</th><th>研究</th></tr></thead><tbody><tr v-for="(item, index) in signals" :key="String(item.id || itemCode(item) || index)"><td><strong>{{ itemCode(item) || '—' }}</strong><small>{{ item.name || '—' }}</small></td><td>{{ number(item.score ?? item.signal_score, 4) }}</td><td><span class="tag" :class="String(item.validation_status || item.confidence || '').includes('valid') ? 'good' : 'warn'">{{ item.validation_status || item.confidence || '未验证' }}</span></td><td>{{ item.source || item.provider || '—' }}</td><td><RouterLink class="button ghost compact-button" :to="`/app/research/CN/${encodeURIComponent(String(itemCode(item) || '600519'))}`">打开研究</RouterLink></td></tr></tbody></table></div></div></section>
  </section>
</template>
