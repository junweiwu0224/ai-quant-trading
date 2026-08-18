<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  Download,
  Filter,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import DetailDrawer from '../components/base/DetailDrawer.vue'
import SelectionToolbar from '../components/base/SelectionToolbar.vue'
import FilterBar from '../components/base/FilterBar.vue'

type Mode = 'manual' | 'ai' | 'iwencai'
type Operator = 'gt' | 'lt' | 'gte' | 'lte' | 'between'
type Field = { field: string; label?: string; type?: string }
type Preset = { name: string; desc: string; filters: Array<Record<string, unknown>> }
type Stock = Record<string, unknown>
type FilterItem = { field: string; op: Operator; value: number | [number, number] }
type Condition = { field: string; op: Operator; value: number | null; upper: number | null }
type ApiPayload = { success?: boolean; error?: string; stocks?: Stock[]; total?: number; [key: string]: unknown }
type AIStatus = { trained?: boolean; feature_count?: number; features?: string[]; [key: string]: unknown }
type AIStock = Stock & { rank?: number; probability?: number; risk_score?: number; key_factors?: Record<string, unknown> }
type IwencaiPayload = { success?: boolean; data?: Stock[]; total?: number; error?: string; message?: string }

const mode = ref<Mode>('manual')
const presets = ref<Preset[]>([])
const fields = ref<Field[]>([])
const stocks = ref<Stock[]>([])
const selectedPreset = ref('')
const codeInput = ref('')
const conditions = ref<Condition[]>([])
const loading = ref(false)
const metadataLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const total = ref(0)
const resultLabel = ref('尚未运行')
const resultSearch = ref('')
const sortBy = ref('change_pct')
const sortDesc = ref(true)
const addingCode = ref('')
const selectedCodes = ref<string[]>([])
const detailStock = ref<Stock | null>(null)

const aiStatus = ref<AIStatus | null>(null)
const aiModelType = ref('lightgbm')
const aiStocks = ref<AIStock[]>([])
const aiTraining = ref(false)
const aiLoading = ref(false)
const aiTrainingResult = ref<ApiPayload | null>(null)

const iwencaiQuery = ref('')
const iwencaiResult = ref<IwencaiPayload | null>(null)
const iwencaiLoading = ref(false)

const operators: Array<{ value: Operator; label: string }> = [
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lte', label: '小于等于' },
  { value: 'between', label: '区间' },
]

const numericFields = computed(() => fields.value.filter((item) => item.type === 'number'))
const currentPreset = computed(() => presets.value.find((item) => item.name === selectedPreset.value))
const validConditionCount = computed(() => collectFilters().length)
const filteredStocks = computed(() => {
  const query = resultSearch.value.trim().toLowerCase()
  const filtered = stocks.value.filter((stock) => {
    if (!query) return true
    return [stock.code, stock.name, stock.industry]
      .map((value) => String(value ?? '').toLowerCase())
      .some((value) => value.includes(query))
  })
  return [...filtered].sort((left, right) => {
    const a = left[sortBy.value]
    const b = right[sortBy.value]
    const an = numeric(a)
    const bn = numeric(b)
    if (an !== null && bn !== null) return sortDesc.value ? bn - an : an - bn
    return (sortDesc.value ? String(b ?? '') : String(a ?? '')).localeCompare(sortDesc.value ? String(a ?? '') : String(b ?? ''), 'zh-CN')
  })
})
const iwencaiRows = computed(() => (Array.isArray(iwencaiResult.value?.data) ? iwencaiResult.value?.data || [] : []))
const iwencaiColumns = computed(() => {
  const first = iwencaiRows.value[0]
  if (!first) return []
  return Object.keys(first).filter((key) => !key.toLowerCase().includes('url')).slice(0, 8)
})
const iwencaiCodes = computed(() => iwencaiRows.value.map(stockCode).filter(Boolean))
const activeFilterLabel = computed(() => selectedPreset.value || (validConditionCount.value ? `${validConditionCount.value} 条条件` : codeInput.value ? '代码范围' : '未运行'))

function newCondition(): Condition {
  return { field: numericFields.value[0]?.field || '', op: 'gt', value: null, upper: null }
}

function resetConditions() {
  conditions.value = [newCondition()]
}

function fieldLabel(field: string) {
  return fields.value.find((item) => item.field === field)?.label || field || '选择字段'
}

function addCondition() {
  conditions.value.push(newCondition())
}

function removeCondition(index: number) {
  if (conditions.value.length === 1) {
    resetConditions()
    return
  }
  conditions.value.splice(index, 1)
}

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function collectFilters(): FilterItem[] {
  const result: FilterItem[] = []
  for (const condition of conditions.value) {
    const value = numeric(condition.value)
    if (!condition.field || value === null) continue
    if (condition.op === 'between') {
      const upper = numeric(condition.upper)
      if (upper !== null) result.push({ field: condition.field, op: condition.op, value: [value, upper] })
      continue
    }
    result.push({ field: condition.field, op: condition.op, value })
  }
  return result
}

function loadFilters(filters: Array<Record<string, unknown>>) {
  const parsed = filters.flatMap((filter) => {
    const field = String(filter.field || '')
    const op = String(filter.op || 'gt') as Operator
    const raw = filter.value
    const values = Array.isArray(raw) ? raw : [raw]
    const value = numeric(values[0])
    const upper = numeric(values[1])
    if (!field || !operators.some((item) => item.value === op) || value === null) return []
    return [{ field, op, value, upper }]
  })
  conditions.value = parsed.length ? parsed : [newCondition()]
}

function displayNumber(value: unknown, digits = 2, suffix = '') {
  const parsed = numeric(value)
  if (parsed === null) return '—'
  return `${parsed.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`
}

function stockCode(stock: Stock) {
  const value = stock.code ?? stock.symbol ?? stock.stock_code ?? stock['股票代码']
  const match = String(value ?? '').match(/\d{6}/)
  return match?.[0] || ''
}

function stockField(stock: Stock, keys: string[]) {
  for (const key of keys) if (stock[key] !== undefined && stock[key] !== null && stock[key] !== '') return stock[key]
  return null
}

function stockName(stock: Stock) {
  return stockField(stock, ['name', 'stock_name', '股票简称']) || '—'
}

function changeClass(value: unknown) {
  const parsed = numeric(value)
  return parsed === null ? '' : parsed > 0 ? 'good' : parsed < 0 ? 'bad' : ''
}

function aiPercent(value: unknown) {
  const parsed = numeric(value)
  return displayNumber(parsed === null ? null : parsed * 100, 1, '%')
}

function resultNumber(stock: Stock, keys: string[], digits = 2, suffix = '') {
  return displayNumber(stockField(stock, keys), digits, suffix)
}

function sortResults(field: string) {
  if (sortBy.value === field) sortDesc.value = !sortDesc.value
  else {
    sortBy.value = field
    sortDesc.value = true
  }
}

function sortMark(field: string) {
  return sortBy.value === field ? (sortDesc.value ? ' ↓' : ' ↑') : ''
}

function toggleSelected(stock: Stock) {
  const code = stockCode(stock)
  if (!code) return
  selectedCodes.value = selectedCodes.value.includes(code)
    ? selectedCodes.value.filter((item) => item !== code)
    : [...selectedCodes.value, code]
}

function clearSelection() {
  selectedCodes.value = []
}

function openStock(stock: Stock) {
  detailStock.value = stock
}

function clearFilter() {
  selectedPreset.value = ''
  codeInput.value = ''
  resultSearch.value = ''
  resetConditions()
}

async function loadMetadata() {
  metadataLoading.value = true
  errorMessage.value = ''
  const [presetResult, fieldResult] = await Promise.allSettled([api.screenerPresets(), api.screenerFields()])
  if (presetResult.status === 'fulfilled') {
    presets.value = (presetResult.value.presets || []).map((item) => ({
      name: String(item.name || ''),
      desc: String(item.desc || ''),
      filters: Array.isArray(item.filters) ? item.filters as Array<Record<string, unknown>> : [],
    })).filter((item) => item.name)
  }
  if (fieldResult.status === 'fulfilled') fields.value = (fieldResult.value.fields || []) as Field[]
  if (presetResult.status === 'rejected' && fieldResult.status === 'rejected') errorMessage.value = '筛选元数据暂不可用，请刷新后重试。'
  if (!conditions.value.length) resetConditions()
  metadataLoading.value = false
}

async function applyResponse(response: ApiPayload, label: string) {
  if (response.success === false) throw new Error(String(response.error || '筛选执行失败'))
  stocks.value = Array.isArray(response.stocks) ? response.stocks : []
  total.value = numeric(response.total) || 0
  resultLabel.value = label
  if (!stocks.value.length) noticeMessage.value = '没有返回候选。数据源为空时不会伪造候选结果。'
  else noticeMessage.value = `已读取 ${total.value || stocks.value.length} 个研究候选。`
}

async function run() {
  loading.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const codes = codeInput.value.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean)
    if (!selectedPreset.value && !codes.length && !validConditionCount.value) throw new Error('请至少选择预设、输入代码或添加一个有效条件。')
    const response = selectedPreset.value
      ? await api.runScreenerPreset({ preset_name: selectedPreset.value, page_size: 100 })
      : await api.runScreener({ codes, filters: collectFilters(), page_size: 100, sort_by: sortBy.value, sort_desc: sortDesc.value })
    await applyResponse(response as ApiPayload, selectedPreset.value || '自定义条件')
  } catch (error) {
    stocks.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '筛选执行失败'
  } finally {
    loading.value = false
  }
}

async function runPreset(preset: Preset) {
  selectedPreset.value = preset.name
  loadFilters(preset.filters)
  await run()
}

function clearResult() {
  selectedPreset.value = ''
  codeInput.value = ''
  resultSearch.value = ''
  stocks.value = []
  total.value = 0
  resultLabel.value = '尚未运行'
  resetConditions()
  noticeMessage.value = '已清空筛选输入和结果。'
}

async function addToWatchlist(code: string) {
  if (!code) return
  addingCode.value = code
  errorMessage.value = ''
  try {
    await api.addWatchlist(code)
    noticeMessage.value = `${code} 已加入当前 workspace 自选。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加入自选失败'
  } finally {
    addingCode.value = ''
  }
}

async function addCodesToWatchlist(codes: string[]) {
  const unique = [...new Set(codes.filter(Boolean))]
  if (!unique.length) {
    errorMessage.value = '当前结果没有可加入自选的代码。'
    return
  }
  addingCode.value = 'bulk'
  errorMessage.value = ''
  let success = 0
  try {
    for (const code of unique) {
      await api.addWatchlist(code)
      success += 1
    }
    noticeMessage.value = `已将 ${success} 个候选加入当前 workspace 自选。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : `已加入 ${success} 个，批量操作中断。`
  } finally {
    addingCode.value = ''
  }
}

function csvValue(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

function exportCsv() {
  if (!stocks.value.length) {
    errorMessage.value = '没有可导出的候选结果。'
    return
  }
  const columns: Array<[string, string]> = [
    ['代码', 'code'], ['名称', 'name'], ['行业', 'industry'], ['最新价', 'price'], ['涨跌幅%', 'change_pct'],
    ['PE', 'pe_ratio'], ['PB', 'pb_ratio'], ['市值(亿)', 'market_cap'], ['换手率%', 'turnover_rate'],
  ]
  const rows = [columns.map(([label]) => csvValue(label)).join(',')]
  for (const stock of stocks.value) rows.push(columns.map(([, key]) => csvValue(stock[key])).join(','))
  const blob = new Blob([`\ufeff${rows.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `选股结果_${new Date().toISOString().slice(0, 10)}.csv`
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  noticeMessage.value = 'CSV 已生成并下载。'
}

async function refreshAIStatus() {
  try {
    aiStatus.value = await api.alphaModelStatus() as AIStatus
  } catch (error) {
    aiStatus.value = null
    errorMessage.value = error instanceof Error ? error.message : 'AI 模型状态读取失败'
  }
}

async function trainAIModel() {
  aiTraining.value = true
  errorMessage.value = ''
  try {
    const response = await api.alphaTrainGlobal({ model_type: aiModelType.value }) as ApiPayload
    if (response.success === false) throw new Error(String(response.error || 'AI 模型训练失败'))
    aiTrainingResult.value = response
    noticeMessage.value = `AI 截面模型训练完成：${response.n_samples || '—'} 个样本，${response.n_features || '—'} 个特征。`
    await refreshAIStatus()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'AI 模型训练失败'
  } finally {
    aiTraining.value = false
  }
}

async function runAIPredict() {
  aiLoading.value = true
  errorMessage.value = ''
  try {
    const response = await api.alphaScreenAi(20) as ApiPayload
    if (response.success === false) throw new Error(String(response.error || 'AI 选股失败'))
    aiStocks.value = Array.isArray(response.stocks) ? response.stocks as AIStock[] : []
    noticeMessage.value = aiStocks.value.length ? `AI 返回 ${aiStocks.value.length} 个研究候选。` : 'AI 没有返回候选；未配置或数据不足时不会伪造结果。'
  } catch (error) {
    aiStocks.value = []
    errorMessage.value = error instanceof Error ? error.message : 'AI 选股失败'
  } finally {
    aiLoading.value = false
  }
}

function keyFactor(stock: AIStock) {
  const factors = stock.key_factors || {}
  const item = Object.entries(factors).sort((left, right) => Math.abs(numeric(right[1]) || 0) - Math.abs(numeric(left[1]) || 0))[0]
  return item ? `${item[0]}：${displayNumber(item[1], 2)}` : '—'
}

async function runIwencai() {
  if (!iwencaiQuery.value.trim()) return
  iwencaiLoading.value = true
  errorMessage.value = ''
  try {
    const response = await api.iwencai(iwencaiQuery.value.trim()) as IwencaiPayload
    iwencaiResult.value = response
    if (response.success === false) throw new Error(String(response.error || '问财查询失败'))
    noticeMessage.value = response.data?.length ? `问财返回 ${response.data.length} 个候选，可导入筛选器复核。` : String(response.message || '问财没有返回候选。')
  } catch (error) {
    iwencaiResult.value = null
    errorMessage.value = error instanceof Error ? error.message : '问财查询失败'
  } finally {
    iwencaiLoading.value = false
  }
}

async function importIwencaiPool() {
  const codes = iwencaiCodes.value
  if (!codes.length) {
    errorMessage.value = '问财结果中没有识别到 6 位股票代码。'
    return
  }
  mode.value = 'manual'
  selectedPreset.value = ''
  codeInput.value = codes.join(', ')
  resetConditions()
  loading.value = true
  errorMessage.value = ''
  try {
    await applyResponse(await api.runScreener({ codes, filters: [], page_size: 100 }) as ApiPayload, `问财：${iwencaiQuery.value.trim()}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '问财候选导入失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadMetadata()
  await refreshAIStatus()
})
</script>

<template>
  <section class="screener-page">
    <div class="page-head">
      <div>
        <RouterLink to="/app/workflows" class="muted small"><ArrowLeft :size="14" />返回工作流目录</RouterLink>
        <h1>条件筛选与 AI 选股</h1>
        <p>把预设、可编辑条件、问财候选池和截面模型放在同一个研究工作流里；结果只生成候选，不直接改变决策、推送或订单。</p>
      </div>
      <div class="head-actions"><span class="tag warn">研究候选</span><button class="button" type="button" :disabled="metadataLoading" @click="loadMetadata"><RefreshCw :size="16" :class="{ spin: metadataLoading }" />刷新字段</button></div>
    </div>

    <div class="screener-boundary panel"><div class="screener-boundary-icon"><ShieldCheck :size="17" /></div><div><strong>安全边界保持不变</strong><p>选股结果需要回到单股研究、验证和确定性策略流程。此页不会创建自动推送资格、交易指令或实盘订单。</p></div><div class="screener-boundary-meta"><span>候选只读</span><span>AI decision_effect: none</span></div></div>
    <FilterBar label="当前筛选" :value="activeFilterLabel" @clear="clearFilter" />
    <div v-if="errorMessage" class="error-box" role="alert">{{ errorMessage }}</div>
    <div v-if="noticeMessage" class="ai-notice" role="status"><CheckCircle2 :size="16" />{{ noticeMessage }}</div>

    <div class="summary-strip screener-summary"><div class="summary-item"><span>当前结果</span><strong>{{ total || '—' }}</strong><small>{{ resultLabel }}</small></div><div class="summary-item"><span>条件数量</span><strong>{{ validConditionCount || '—' }}</strong><small>{{ numericFields.length }} 个数值字段可用</small></div><div class="summary-item"><span>AI 模型</span><strong>{{ aiStatus?.trained ? '已就绪' : '未训练' }}</strong><small>{{ aiStatus?.feature_count || '—' }} 个特征</small></div><div class="summary-item"><span>写入权限</span><strong>人工确认</strong><small>仅显式加入自选</small></div></div>

    <nav class="workspace-tabs" aria-label="选股工作区">
      <button type="button" :class="{ active: mode === 'manual' }" @click="mode = 'manual'"><Filter :size="15" />条件构建器</button>
      <button type="button" :class="{ active: mode === 'ai' }" @click="mode = 'ai'; refreshAIStatus()"><Bot :size="15" />AI 截面选股</button>
      <button type="button" :class="{ active: mode === 'iwencai' }" @click="mode = 'iwencai'"><Search :size="15" />问财候选池</button>
    </nav>

    <template v-if="mode === 'manual'">
      <section class="panel screener-input-panel">
        <div class="panel-head"><div><h2>条件构建器</h2><p>预设可以直接运行，也可以载入后继续编辑；代码范围可与条件同时提交。</p></div><span class="tag">{{ fields.length }} 个字段</span></div>
        <div class="panel-body">
          <div class="screener-preset-list"><button v-for="preset in presets" :key="preset.name" type="button" class="screener-preset" :class="{ active: selectedPreset === preset.name }" :title="preset.desc" :disabled="loading" @click="runPreset(preset)"><strong>{{ preset.name }}</strong><small>{{ preset.desc }}</small></button></div>
          <div class="field-grid screener-scope-grid"><div class="field"><label for="screener-preset">当前预设</label><select id="screener-preset" v-model="selectedPreset" class="field-select"><option value="">自定义条件</option><option v-for="preset in presets" :key="preset.name" :value="preset.name">{{ preset.name }}</option></select></div><div class="field"><label for="screener-codes">代码范围（可选）</label><input id="screener-codes" v-model="codeInput" class="field-input" placeholder="600519, 000001；留空表示全市场" /></div></div>
          <div class="screener-condition-head"><div><strong>筛选条件</strong><span>{{ validConditionCount ? `已配置 ${validConditionCount} 条有效条件` : '至少填写一条条件，或使用代码范围' }}</span></div><button class="button ghost" type="button" @click="addCondition"><Plus :size="15" />添加条件</button></div>
          <div class="screener-conditions"><div v-for="(condition, index) in conditions" :key="index" class="screener-condition-row"><select v-model="condition.field" class="field-select" :aria-label="`第 ${index + 1} 条条件字段`"><option value="">选择字段</option><option v-for="field in numericFields" :key="field.field" :value="field.field">{{ field.label || field.field }}</option></select><select v-model="condition.op" class="field-select" :aria-label="`第 ${index + 1} 条条件运算符`"><option v-for="operator in operators" :key="operator.value" :value="operator.value">{{ operator.label }}</option></select><input v-model.number="condition.value" class="field-input" type="number" step="any" :placeholder="condition.op === 'between' ? '最小值' : '数值'" :aria-label="`${fieldLabel(condition.field)}数值`" /><input v-if="condition.op === 'between'" v-model.number="condition.upper" class="field-input" type="number" step="any" placeholder="最大值" aria-label="区间最大值" /><button class="icon-button compact-icon" type="button" title="移除条件" aria-label="移除条件" @click="removeCondition(index)"><Trash2 :size="14" /></button></div></div>
          <div v-if="currentPreset" class="data-source screener-preset-description"><span><Sparkles :size="14" />{{ currentPreset.desc }}</span></div>
          <div class="form-actions"><button class="button primary" type="button" :disabled="loading" @click="run"><Play :size="15" />{{ loading ? '筛选中' : '运行筛选' }}</button><button class="button" type="button" :disabled="loading" @click="clearResult">清空</button></div>
        </div>
      </section>

      <section class="panel screener-result-panel">
        <div class="panel-head"><div><h2>候选结果</h2><p>共 {{ total || 0 }} 个候选；表格支持搜索、排序和显式加入自选。</p></div><div class="head-actions"><span class="tag">{{ resultLabel }}</span><button class="button ghost compact-button" type="button" :disabled="!stocks.length" @click="exportCsv"><Download :size="14" />导出 CSV</button><button class="button ghost compact-button" type="button" :disabled="!stocks.length || addingCode === 'bulk'" @click="addCodesToWatchlist(stocks.map(stockCode))"><Star :size="14" />全部加自选</button></div></div>
        <div class="panel-body"><div v-if="stocks.length" class="inline-search screener-result-tools"><input v-model="resultSearch" aria-label="搜索候选结果" placeholder="搜索代码、名称或行业" /><span class="tag">显示 {{ filteredStocks.length }} / {{ stocks.length }}</span></div><div v-if="!stocks.length" class="empty"><strong>暂无候选</strong><span>选择预设、添加条件、输入代码或导入问财候选池后运行。</span></div><div v-else-if="!filteredStocks.length" class="empty">没有匹配当前搜索词。</div><div v-else class="table-scroll"><table class="decision-table screener-table"><thead><tr><th><input type="checkbox" aria-label="选择全部当前候选" :checked="filteredStocks.length > 0 && filteredStocks.every((stock) => selectedCodes.includes(stockCode(stock)))" @change="selectedCodes = ($event.target as HTMLInputElement).checked ? filteredStocks.map(stockCode).filter(Boolean) : []" /></th><th><button type="button" class="table-sort" @click="sortResults('code')">代码{{ sortMark('code') }}</button></th><th>名称</th><th>行业</th><th><button type="button" class="table-sort" @click="sortResults('price')">最新价{{ sortMark('price') }}</button></th><th><button type="button" class="table-sort" @click="sortResults('change_pct')">涨跌幅{{ sortMark('change_pct') }}</button></th><th>PE</th><th>PB</th><th>市值(亿)</th><th>换手率</th><th>操作</th></tr></thead><tbody><tr v-for="stock in filteredStocks" :key="stockCode(stock) || String(stock.name)"><td><input type="checkbox" :aria-label="`选择 ${stockCode(stock) || stockName(stock)}`" :checked="selectedCodes.includes(stockCode(stock))" @change="toggleSelected(stock)" /></td><td class="symbol"><button type="button" class="table-link" @click="openStock(stock)">{{ stockCode(stock) || '—' }}</button></td><td>{{ stockName(stock) }}</td><td>{{ stock.industry || '—' }}</td><td>{{ resultNumber(stock, ['price', '最新价'], 2) }}</td><td :class="changeClass(stock.change_pct)">{{ resultNumber(stock, ['change_pct', '涨跌幅'], 2, '%') }}</td><td>{{ resultNumber(stock, ['pe_ratio', '市盈率'], 2) }}</td><td>{{ resultNumber(stock, ['pb_ratio', '市净率'], 2) }}</td><td>{{ resultNumber(stock, ['market_cap', '总市值'], 2) }}</td><td>{{ resultNumber(stock, ['turnover_rate', '换手率'], 2, '%') }}</td><td><button class="button ghost compact-button" type="button" :disabled="addingCode === stockCode(stock) || addingCode === 'bulk'" @click="addToWatchlist(stockCode(stock))"><Star :size="13" />加入</button></td></tr></tbody></table></div></div>
      </section>
      <SelectionToolbar class="mobile-task-bar" :count="selectedCodes.length" label="个候选" @clear="clearSelection"><button class="button" type="button" :disabled="addingCode === 'bulk'" @click="addCodesToWatchlist(selectedCodes)"><Star :size="13" />加入自选</button><button class="button" type="button" @click="detailStock = filteredStocks.find((stock) => stockCode(stock) === selectedCodes[0]) || null">查看首项</button></SelectionToolbar>
      <DetailDrawer :open="Boolean(detailStock)" :title="detailStock ? `${stockCode(detailStock)} ${stockName(detailStock)}` : '候选详情'" eyebrow="SCREENING CANDIDATE" @close="detailStock = null"><div v-if="detailStock" class="screener-detail"><div class="detail-metric"><span>行业</span><strong>{{ detailStock.industry || '—' }}</strong></div><div class="detail-metric"><span>最新价</span><strong>{{ resultNumber(detailStock, ['price', '最新价'], 2) }}</strong></div><div class="detail-metric"><span>涨跌幅</span><strong :class="changeClass(detailStock.change_pct)">{{ resultNumber(detailStock, ['change_pct', '涨跌幅'], 2, '%') }}</strong></div><div class="detail-metric"><span>估值</span><strong>PE {{ resultNumber(detailStock, ['pe_ratio', '市盈率'], 2) }} · PB {{ resultNumber(detailStock, ['pb_ratio', '市净率'], 2) }}</strong></div><p class="muted">候选只用于研究排序。打开单股研究后，继续查看证据、验证和资格状态。</p><RouterLink class="button primary" :to="`/app/research/CN/${encodeURIComponent(stockCode(detailStock))}`">进入单股研究</RouterLink></div></DetailDrawer>
    </template>

    <template v-else-if="mode === 'ai'">
      <section class="panel"><div class="panel-head"><div><h2>AI 截面模型</h2><p>模型训练和预测沿用 Alpha API；概率、风险和因子仅作研究解释，不拥有确定性决策权。</p></div><span class="tag" :class="aiStatus?.trained ? 'good' : 'warn'">{{ aiStatus?.trained ? '模型已就绪' : '需要训练' }}</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="ai-model-type">模型类型</label><select id="ai-model-type" v-model="aiModelType" class="field-select"><option value="lightgbm">LightGBM</option><option value="xgboost">XGBoost</option><option value="ensemble">Ensemble</option></select></div><div class="field"><label>模型元数据</label><div class="screener-status-line"><span>{{ aiStatus?.feature_count || '—' }} 个特征</span><span>{{ aiStatus?.trained ? '已有缓存模型' : '暂无可用缓存' }}</span></div></div></div><div class="form-actions"><button class="button" type="button" :disabled="aiTraining" @click="refreshAIStatus"><RefreshCw :size="15" :class="{ spin: aiTraining }" />读取状态</button><button class="button primary" type="button" :disabled="aiTraining" @click="trainAIModel"><Bot :size="15" />{{ aiTraining ? '训练中' : '训练全市场模型' }}</button><button class="button" type="button" :disabled="aiLoading || !aiStatus?.trained" @click="runAIPredict"><Play :size="15" />{{ aiLoading ? '预测中' : '运行 AI 选股' }}</button></div><div v-if="aiTrainingResult" class="result-code screener-training-result">{{ JSON.stringify(aiTrainingResult, null, 2) }}</div></div></section>
      <section class="panel screener-result-panel"><div class="panel-head"><div><h2>AI 推荐候选</h2><p>按预测概率排序；风险分数不是止损指令，下一步应打开研究并进行验证。</p></div><div class="head-actions"><span class="tag">{{ aiStocks.length }} 个候选</span><button class="button ghost compact-button" type="button" :disabled="!aiStocks.length || addingCode === 'bulk'" @click="addCodesToWatchlist(aiStocks.map(stockCode))"><Star :size="14" />全部加自选</button></div></div><div class="panel-body"><div v-if="!aiStocks.length" class="empty"><strong>暂无 AI 候选</strong><span>先检查模型状态并显式运行预测；模型不可用时保持空状态。</span></div><div v-else class="table-scroll"><table class="decision-table screener-table"><thead><tr><th>排名</th><th>代码</th><th>名称 / 行业</th><th>预测概率</th><th>风险分数</th><th>关键因子</th><th>操作</th></tr></thead><tbody><tr v-for="stock in aiStocks" :key="stockCode(stock) || String(stock.rank)"><td class="symbol">{{ stock.rank ?? '—' }}</td><td>{{ stockCode(stock) || '—' }}</td><td><strong>{{ stockName(stock) }}</strong><small>{{ stock.industry || '—' }}</small></td><td class="good">{{ aiPercent(stock.probability) }}</td><td>{{ aiPercent(stock.risk_score) }}</td><td>{{ keyFactor(stock) }}</td><td><button class="button ghost compact-button" type="button" :disabled="addingCode === stockCode(stock) || addingCode === 'bulk'" @click="addToWatchlist(stockCode(stock))"><Star :size="13" />加入</button></td></tr></tbody></table></div></div></section>
    </template>

    <template v-else>
      <section class="panel"><div class="panel-head"><div><h2>问财自然语言候选池</h2><p>保留问财原始结果和来源语义；导入后会再次经过本地筛选接口，无法识别代码时不会猜测。</p></div><Search :size="18" class="faint" /></div><div class="panel-body"><div class="inline-search"><input v-model="iwencaiQuery" aria-label="问财查询" placeholder="例如：近 5 日涨幅超过 10% 的股票" @keydown.enter.prevent="runIwencai" /><button class="button primary" type="button" :disabled="iwencaiLoading || !iwencaiQuery.trim()" @click="runIwencai"><Search :size="15" />{{ iwencaiLoading ? '查询中' : '查询问财' }}</button></div><div class="form-actions"><button class="button" type="button" :disabled="!iwencaiCodes.length" @click="importIwencaiPool"><Filter :size="15" />导入条件筛选器（{{ iwencaiCodes.length }}）</button><span class="tag warn">外部数据源可能限流或不可用</span></div></div></section>
      <section class="panel screener-result-panel"><div class="panel-head"><div><h2>问财结果</h2><p>{{ iwencaiResult?.message || `当前返回 ${iwencaiRows.length} 条，最多展示前 50 条。` }}</p></div><span class="tag">原始候选</span></div><div class="panel-body"><div v-if="!iwencaiResult" class="empty"><strong>还没有查询</strong><span>输入自然语言条件后，结果会在这里保留。</span></div><div v-else-if="!iwencaiRows.length" class="empty">问财没有返回可展示候选。</div><div v-else class="table-scroll"><table class="decision-table screener-table"><thead><tr><th v-for="column in iwencaiColumns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in iwencaiRows" :key="`${stockCode(row)}-${index}`"><td v-for="column in iwencaiColumns" :key="column">{{ row[column] ?? '—' }}</td></tr></tbody></table></div></div></section>
    </template>
  </section>
</template>
