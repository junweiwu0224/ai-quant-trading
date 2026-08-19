<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, Code2, Download, Edit3, FilePlus2, FlaskConical, Play, RefreshCw, RotateCcw, Save, ShieldCheck, Trash2, Upload, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'

type Row = Record<string, any>
type Tab = 'catalog' | 'editor' | 'optimization' | 'ensemble' | 'history'

const tab = ref<Tab>('catalog')
const strategies = ref<Row[]>([])
const selected = ref<Row | null>(null)
const versions = ref<Row[]>([])
const records = ref<Row[]>([])
const result = ref<Row | null>(null)
const validation = ref<Row | null>(null)
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const deleteId = ref('')
const importText = ref('')
const form = ref({ name: '', label: '', type: '自定义', description: '', params: '{}', code: '' })
const optimizeForm = ref({ codes: '000001', start_date: '2023-01-01', end_date: '2024-12-31', initial_cash: 1000000, param_ranges: '{"short_window":[5,10],"long_window":[20,30]}', metric: 'sharpe_ratio' })
const ensembleForm = ref({ codes: '000001', start_date: '2023-01-01', end_date: '2024-12-31', initial_cash: 1000000, buy_threshold: 0.3, sell_threshold: -0.3 })
const ensembleSelection = ref<string[]>([])

const isEditing = computed(() => Boolean(form.value.name))

function codes(value: string) {
  return [...new Set(value.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean))]
}

function json(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

function resetEditor() {
  selected.value = null
  form.value = { name: '', label: '', type: '自定义', description: '', params: '{}', code: '' }
  validation.value = null
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    strategies.value = (await api.strategies()) as Row[]
    if (!ensembleSelection.value.length) ensembleSelection.value = strategies.value.filter((item) => item.builtin).slice(0, 2).map((item) => String(item.name))
    if (selected.value) {
      const current = strategies.value.find((item) => item.name === selected.value?.name)
      if (current) await selectStrategy(current)
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略目录加载失败'
  } finally {
    loading.value = false
  }
}

async function selectStrategy(strategy: Row) {
  try {
    const detail = await api.strategy(String(strategy.name))
    selected.value = detail
    form.value = { name: String(detail.name || ''), label: String(detail.label || detail.name || ''), type: String(detail.type || '自定义'), description: String(detail.description || ''), params: json(detail.params || {}), code: String(detail.code || '') }
    versions.value = (await api.strategyVersions(String(detail.name))) as Row[]
    records.value = (await api.strategyRecords(String(detail.name))) as Row[]
    tab.value = 'editor'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略详情加载失败'
  }
}

function newStrategy() {
  resetEditor()
  tab.value = 'editor'
}

function parseParams() {
  try {
    const parsed = JSON.parse(form.value.params || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('参数必须是 JSON 对象')
    return parsed
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : '参数 JSON 无效')
  }
}

async function saveStrategy() {
  if (!form.value.name.trim() || !form.value.label.trim()) {
    message.value = '策略标识和显示名称不能为空'
    return
  }
  saving.value = true
  message.value = ''
  try {
    const payload = { name: form.value.name.trim(), label: form.value.label.trim(), type: form.value.type, description: form.value.description, params: parseParams(), code: form.value.code || undefined }
    if (selected.value?.builtin) await api.updateStrategy(form.value.name, { label: payload.label, description: payload.description, params: payload.params })
    else if (selected.value) await api.updateStrategy(form.value.name, payload)
    else await api.createStrategy(payload)
    message.value = '策略已保存；建议立即保存一个版本'
    await load()
    const saved = strategies.value.find((item) => item.name === form.value.name)
    if (saved) await selectStrategy(saved)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略保存失败'
  } finally {
    saving.value = false
  }
}

async function deleteStrategy(strategy: Row) {
  const name = String(strategy.name)
  if (deleteId.value !== name) {
    deleteId.value = name
    return
  }
  saving.value = true
  try {
    await api.deleteStrategy(name)
    message.value = '自定义策略已删除'
    deleteId.value = ''
    resetEditor()
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略删除失败'
  } finally {
    saving.value = false
  }
}

async function validateCode() {
  saving.value = true
  try {
    validation.value = await api.validateStrategyCode(form.value.code)
    message.value = validation.value.valid ? '策略代码校验通过' : String(validation.value.error || '策略代码未通过校验')
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略代码校验失败'
  } finally {
    saving.value = false
  }
}

async function saveVersion() {
  if (!form.value.name) return
  saving.value = true
  try {
    await api.saveStrategyVersion({ strategy_name: form.value.name, label: `${form.value.label} · 手动版本`, description: form.value.description, params: parseParams(), code: form.value.code })
    versions.value = (await api.strategyVersions(form.value.name)) as Row[]
    message.value = '策略版本已保存'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '版本保存失败'
  } finally {
    saving.value = false
  }
}

async function rollback(version: Row) {
  if (!form.value.name) return
  saving.value = true
  try {
    await api.rollbackStrategyVersion({ strategy_name: form.value.name, version: Number(version.version) })
    message.value = `已从 v${version.version} 创建回滚版本`
    await selectStrategy({ name: form.value.name })
  } catch (error) {
    message.value = error instanceof Error ? error.message : '版本回滚失败'
  } finally {
    saving.value = false
  }
}

async function runOptimize() {
  if (!form.value.name) return
  loading.value = true
  try {
    result.value = await api.optimizeStrategy({ strategy: form.value.name, ...optimizeForm.value, codes: codes(optimizeForm.value.codes), param_ranges: JSON.parse(optimizeForm.value.param_ranges), top_n: 8 })
    tab.value = 'optimization'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '参数优化失败，请检查 JSON 和日期'
  } finally {
    loading.value = false
  }
}

async function runEnsemble() {
  if (!ensembleSelection.value.length) {
    message.value = '至少选择一个策略'
    return
  }
  loading.value = true
  try {
    result.value = await api.ensembleBacktest({ strategies: ensembleSelection.value.map((name) => ({ name, weight: 1 })), ...ensembleForm.value, codes: codes(ensembleForm.value.codes), position_pct: 0.9 })
  } catch (error) {
    message.value = error instanceof Error ? error.message : '组合策略回测失败'
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  records.value = (await api.strategyRecords(form.value.name)) as Row[]
  versions.value = (await api.strategyVersions(form.value.name)) as Row[]
}

async function exportAll() {
  try {
    const response = await api.exportStrategies()
    const payload = JSON.stringify(response.data || response, null, 2)
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `strategies-${new Date().toISOString().slice(0, 10)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    message.value = '策略已导出'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '策略导出失败'
  }
}

async function importAll() {
  try {
    const payload = JSON.parse(importText.value)
    const response = await api.importStrategies({ ...payload, overwrite: false })
    message.value = response.success === false ? String(response.error || '导入失败') : '策略导入完成（同名策略未覆盖）'
    await load()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '导入内容不是合法 JSON'
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><RouterLink to="/app/validation" class="muted small"><ArrowLeft :size="14" />验证工作区</RouterLink><h1>策略工作台</h1><p>策略目录、代码、版本、优化和 ensemble 回测统一在这里；所有结果仍需验证，不会自动进入订单或推送资格。</p></div><div class="head-actions"><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />刷新</button><RouterLink class="button ghost" to="/app/ai"><Code2 :size="15" />AI 研究助手</RouterLink></div></div>
    <div v-if="message" class="error-box" role="status">{{ message }}</div>
    <nav class="workspace-tabs" aria-label="策略工作台视图"><button type="button" :class="{ active: tab === 'catalog' }" @click="tab = 'catalog'"><FlaskConical :size="15" />策略目录</button><button type="button" :class="{ active: tab === 'editor' }" @click="tab = 'editor'"><Edit3 :size="15" />编辑与版本</button><button type="button" :class="{ active: tab === 'optimization' }" @click="tab = 'optimization'"><Play :size="15" />参数优化</button><button type="button" :class="{ active: tab === 'ensemble' }" @click="tab = 'ensemble'"><ShieldCheck :size="15" />组合回测</button><button type="button" :class="{ active: tab === 'history' }" @click="tab = 'history'; loadHistory()"><RotateCcw :size="15" />版本与记录</button></nav>

    <template v-if="tab === 'catalog'">
      <section class="panel"><div class="panel-head"><div><h2>策略目录</h2><p>内置策略可以修改参数但不能删除；自定义策略支持完整维护。</p></div><div class="head-actions"><button class="button" type="button" @click="exportAll"><Download :size="15" />导出</button><button class="button primary" type="button" @click="newStrategy"><FilePlus2 :size="15" />新建策略</button></div></div><div class="panel-body"><div v-if="!strategies.length" class="empty">暂无策略目录。</div><div v-else class="strategy-grid"><article v-for="strategy in strategies" :key="strategy.name" class="strategy-card"><div class="strategy-card-head"><div><strong>{{ strategy.label || strategy.name }}</strong><small>{{ strategy.name }} · {{ strategy.type || '策略' }}</small></div><span class="tag" :class="strategy.builtin ? 'good' : 'warn'">{{ strategy.builtin ? '内置' : '自定义' }}</span></div><p>{{ strategy.description || '暂无策略说明' }}</p><pre class="result-code strategy-params">{{ json(strategy.params || {}) }}</pre><div class="form-actions"><button class="button primary" type="button" @click="selectStrategy(strategy)"><Edit3 :size="14" />打开</button><button v-if="!strategy.builtin" class="button danger" type="button" @click="deleteStrategy(strategy)"><Trash2 :size="14" />{{ deleteId === strategy.name ? '再次确认删除' : '删除' }}</button><button v-if="strategy.builtin && deleteId === strategy.name" class="button ghost" type="button" @click="deleteId = ''"><X :size="14" />取消</button></div></article></div></div></section>
      <section class="section-grid two" style="margin-top:18px"><section class="panel"><div class="panel-head"><div><h2>导入策略</h2><p>粘贴导出的 JSON；导入默认不覆盖同名策略。</p></div><Upload :size="18" class="faint" /></div><div class="panel-body"><textarea v-model="importText" class="code-input" rows="8" placeholder='{"custom": [{"name": "my_strategy"}]}' /><div class="form-actions"><button class="button" type="button" :disabled="!importText.trim()" @click="importAll"><Upload :size="15" />导入</button></div></div></section><section class="panel"><div class="panel-head"><div><h2>安全约束</h2><p>自定义策略代码要经过后端校验，模拟盘和实盘仍是不同入口。</p></div><ShieldCheck :size="18" class="good" /></div><div class="panel-body"><div class="security-note"><CheckCircle2 :size="15" /><span>策略结果只进入回测、验证和人工确认流程，不会被 AI 文本直接提升为可执行动作。</span></div></div></section></section>
    </template>

    <template v-else-if="tab === 'editor'">
      <div class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>{{ isEditing ? `编辑：${form.label || form.name}` : '新建自定义策略' }}</h2><p>保存策略本体后，可单独保存不可变版本。</p></div><button class="button ghost" type="button" @click="resetEditor"><RotateCcw :size="15" />清空</button></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="strategy-name">策略标识</label><input id="strategy-name" v-model="form.name" :disabled="Boolean(selected?.builtin)" placeholder="my_strategy" /></div><div class="field"><label for="strategy-label">显示名称</label><input id="strategy-label" v-model="form.label" placeholder="我的策略" /></div><div class="field"><label for="strategy-type">类型</label><input id="strategy-type" v-model="form.type" /></div></div><div class="field" style="margin-top:13px"><label for="strategy-description">描述</label><textarea id="strategy-description" v-model="form.description" rows="3" /></div><div class="field" style="margin-top:13px"><label for="strategy-params">参数 JSON</label><textarea id="strategy-params" v-model="form.params" class="code-input" rows="7" spellcheck="false" /></div><div class="field" style="margin-top:13px"><label for="strategy-code">自定义代码（可选）</label><textarea id="strategy-code" v-model="form.code" class="code-input" rows="10" spellcheck="false" placeholder="只有自定义策略需要填写代码" /></div><div class="form-actions"><button class="button primary" type="button" :disabled="saving" @click="saveStrategy"><Save :size="15" />保存策略</button><button class="button" type="button" :disabled="saving || !form.code" @click="validateCode"><CheckCircle2 :size="15" />校验代码</button><button class="button" type="button" :disabled="saving || !form.name" @click="saveVersion"><Save :size="15" />保存版本</button></div><div v-if="validation" class="security-note" :class="validation.valid ? 'good' : 'bad'"><CheckCircle2 :size="15" />{{ validation.valid ? '代码校验通过' : validation.error }}</div></div></section><section class="panel"><div class="panel-head"><div><h2>版本列表</h2><p>版本保存不覆盖历史；回滚会创建一个新的版本。</p></div><span class="tag">{{ versions.length }} 个版本</span></div><div class="panel-body"><div v-if="!versions.length" class="empty">暂无版本。保存策略后创建第一个版本。</div><div v-else class="version-list"><article v-for="version in versions" :key="version.id || version.version" class="version-row"><div><strong>v{{ version.version }} · {{ version.label }}</strong><small>{{ version.created_at || '—' }} · {{ version.is_current ? '当前' : '历史' }}</small></div><button v-if="!version.is_current" class="button ghost compact-button" type="button" :disabled="saving" @click="rollback(version)"><RotateCcw :size="14" />回滚</button></article></div></div></section></div>
    </template>

    <template v-else-if="tab === 'optimization'"><section class="panel"><div class="panel-head"><div><h2>参数网格优化</h2><p>后端限制参数组合数；结果只用于比较，不自动修改策略。</p></div><span class="tag warn">显式运行</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label>当前策略</label><input :value="form.name || '先从目录选择策略'" disabled /></div><div class="field"><label>标的</label><input v-model="optimizeForm.codes" /></div><div class="field"><label>开始日期</label><input v-model="optimizeForm.start_date" type="date" /></div><div class="field"><label>结束日期</label><input v-model="optimizeForm.end_date" type="date" /></div><div class="field"><label>初始资金</label><input v-model.number="optimizeForm.initial_cash" type="number" min="1" /></div><div class="field"><label>优化指标</label><select v-model="optimizeForm.metric"><option value="sharpe_ratio">夏普</option><option value="total_return">总收益</option><option value="max_drawdown">最大回撤</option></select></div></div><div class="field" style="margin-top:13px"><label>参数范围 JSON</label><textarea v-model="optimizeForm.param_ranges" class="code-input" rows="5" /></div><div class="form-actions"><button class="button primary" type="button" :disabled="loading || !form.name" @click="runOptimize"><Play :size="15" />运行优化</button></div><pre v-if="result" class="result-code" style="margin-top:16px">{{ json(result) }}</pre><div v-else class="empty" style="margin-top:16px">选择一个策略并运行参数优化。</div></div></section></template>

    <template v-else-if="tab === 'ensemble'"><section class="panel"><div class="panel-head"><div><h2>组合策略回测</h2><p>多个确定性策略按权重聚合；这是回测，不是实时下单。</p></div><ShieldCheck :size="18" class="faint" /></div><div class="panel-body"><div class="strategy-check-grid"><label v-for="strategy in strategies" :key="strategy.name" class="check-control"><input v-model="ensembleSelection" type="checkbox" :value="strategy.name" />{{ strategy.label || strategy.name }}</label></div><div class="field-grid" style="margin-top:16px"><div class="field"><label>标的</label><input v-model="ensembleForm.codes" /></div><div class="field"><label>初始资金</label><input v-model.number="ensembleForm.initial_cash" type="number" min="1" /></div><div class="field"><label>开始日期</label><input v-model="ensembleForm.start_date" type="date" /></div><div class="field"><label>结束日期</label><input v-model="ensembleForm.end_date" type="date" /></div></div><div class="form-actions"><button class="button primary" type="button" :disabled="loading" @click="runEnsemble"><Play :size="15" />运行组合回测</button></div><pre v-if="result" class="result-code" style="margin-top:16px">{{ json(result) }}</pre><div v-else class="empty" style="margin-top:16px">选择策略后运行组合回测。</div></div></section></template>

    <template v-else><section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>版本历史</h2><p>{{ form.name || '选择一个策略后查看版本' }}</p></div></div><div class="panel-body"><div v-if="!versions.length" class="empty">暂无版本。</div><div v-else class="version-list"><div v-for="version in versions" :key="version.id || version.version" class="version-row"><span><strong>v{{ version.version }}</strong><small>{{ version.label }} · {{ version.created_at || '—' }}</small></span><span class="tag" :class="version.is_current ? 'good' : ''">{{ version.is_current ? '当前' : '历史' }}</span></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>回测记录</h2><p>历史结果保持独立，便于复核和比较。</p></div></div><div class="panel-body"><div v-if="!records.length" class="empty">暂无回测记录。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>名称</th><th>策略</th><th>总收益</th><th>回撤</th><th>夏普</th></tr></thead><tbody><tr v-for="record in records" :key="record.id"><td>{{ record.label || record.id }}</td><td>{{ record.strategy_name || '—' }}</td><td>{{ record.total_return ?? '—' }}</td><td>{{ record.max_drawdown ?? '—' }}</td><td>{{ record.sharpe_ratio ?? '—' }}</td></tr></tbody></table></div></div></section></section></template>
  </section>
</template>
