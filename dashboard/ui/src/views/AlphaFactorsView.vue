<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Beaker, Play, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../api/client'

type Row = Record<string, any>
type Mode = 'alpha' | 'factor' | 'formula' | 'basket'

const route = useRoute()
const activeMode = ref<Mode>('alpha')
const mode = computed<Mode>(() => activeMode.value)
const code = ref('000001')
const startDate = ref('2023-01-01')
const endDate = ref('2024-12-31')
const modelType = ref('lightgbm')
const factorName = ref('')
const factorCodes = ref('000001')
const formula = ref('close > MA(close, 20)')
const basketCandidates = ref('[{"code":"000001","name":"平安银行","probability":0.7},{"code":"600519","name":"贵州茅台","probability":0.6}]')
const initialCash = ref(1000000)
const allocation = ref('equal')
const rebalanceDays = ref(5)
const modelStatus = ref<Row | null>(null)
const factors = ref<Row[]>([])
const formulas = ref<Row[]>([])
const factorEval = ref<Row[]>([])
const factorAnalysis = ref<Row | null>(null)
const factorCorrelation = ref<Row | null>(null)
const factorDecay = ref<Row | null>(null)
const prediction = ref<Row | null>(null)
const performance = ref<Row | null>(null)
const walkForward = ref<Row | null>(null)
const modelComparison = ref<Row | null>(null)
const shap = ref<Row | null>(null)
const mined = ref<Row[]>([])
const optimization = ref<Row | null>(null)
const formulaResult = ref<Row | null>(null)
const formulaScreenResult = ref<Row | null>(null)
const basketPlan = ref<Row | null>(null)
const basketResult = ref<Row | null>(null)
const loading = ref(false)
const message = ref('')
const activeTask = ref('')

function list(value: unknown, keys: string[]) {
  if (Array.isArray(value)) return value as Row[]
  if (value && typeof value === 'object') {
    const item = value as Row
    for (const key of keys) if (Array.isArray(item[key])) return item[key] as Row[]
  }
  return []
}
function query() {
  return { code: code.value, start_date: startDate.value, end_date: endDate.value, model_type: modelType.value }
}
function codes() {
  return [...new Set(factorCodes.value.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean))]
}
function numberValue(value: unknown, digits = 4) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}
function json(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2)
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    const [status, factorResponse, formulaResponse] = await Promise.all([api.alphaModelStatus(), api.factorList(), api.alphaFormulaCatalog()])
    modelStatus.value = status
    factors.value = list(factorResponse, ['factors', 'items'])
    formulas.value = list(formulaResponse, ['functions', 'formulas', 'catalog', 'items'])
    if (!factorName.value && factors.value[0]) factorName.value = String(factors.value[0].name)
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Alpha 与因子状态加载失败'
  } finally {
    loading.value = false
  }
}

async function runTask(name: string, operation: () => Promise<void>) {
  loading.value = true
  activeTask.value = name
  message.value = ''
  try { await operation() } catch (error) { message.value = error instanceof Error ? error.message : `${name}失败` } finally { loading.value = false; activeTask.value = '' }
}

function runPredict() { return runTask('预测', async () => { prediction.value = await api.alphaPredict({ ...query(), buy_threshold: 0.6, sell_threshold: 0.4 }) }) }
function runPerformance() { return runTask('绩效', async () => { performance.value = await api.alphaPerformance({ ...query(), buy_threshold: 0.6, sell_threshold: 0.4, initial_cash: initialCash.value }) }) }
function runFactorEval() { return runTask('因子评价', async () => { factorEval.value = await api.alphaFactorEval({ ...query(), forward_period: 5 }) }) }
function runFactorAnalyze() { return runTask('单因子分析', async () => { factorAnalysis.value = await api.factorAnalyze({ factor_name: factorName.value, stock_codes: codes(), start_date: startDate.value, end_date: endDate.value, forward_period: 5 }) }) }
function runCorrelation() { return runTask('因子相关性', async () => { factorCorrelation.value = await api.alphaFactorCorrelation(query()) }) }
function runDecay() { return runTask('因子衰减', async () => { factorDecay.value = await api.alphaFactorDecay({ ...query(), top_n: 10 }) }) }
function runShap() { return runTask('SHAP', async () => { shap.value = await api.alphaShap(query()) }) }
function runWalkForward() { return runTask('Walk-Forward', async () => { walkForward.value = await api.alphaWalkForward({ ...query(), train_days: 252, test_days: 21, step_days: 21 }) }) }
function runModelCompare() { return runTask('模型比较', async () => { modelComparison.value = await api.alphaCompare({ code: code.value, start_date: startDate.value, end_date: endDate.value }) }) }
function runMine() { return runTask('因子挖掘', async () => { mined.value = await api.alphaMine({ ...query(), top_n: 30 }) }) }
function runOptimize() { return runTask('超参优化', async () => { optimization.value = await api.alphaOptimize({ ...query(), n_trials: 50 }) }) }
function evaluateFormula() { return runTask('公式评估', async () => { formulaResult.value = await api.formulaEvaluate({ code: code.value, formula: formula.value, start_date: startDate.value, end_date: endDate.value }) }) }
function screenFormula() { return runTask('公式选股', async () => { formulaScreenResult.value = await api.formulaScreen({ formula: formula.value, codes: codes(), start_date: startDate.value, end_date: endDate.value }) }) }
function parseCandidates() {
  const parsed = JSON.parse(basketCandidates.value)
  if (!Array.isArray(parsed) || !parsed.length) throw new Error('篮子候选必须是非空 JSON 数组')
  return parsed
}
function planBasket() { return runTask('篮子计划', async () => { basketPlan.value = await api.basketPlan({ candidates: parseCandidates(), initial_cash: initialCash.value, allocation: allocation.value, rebalance_days: rebalanceDays.value, start_date: startDate.value, end_date: endDate.value }) }) }
function backtestBasket() { return runTask('篮子回测', async () => { basketResult.value = await api.basketBacktest({ candidates: parseCandidates(), initial_cash: initialCash.value, allocation: allocation.value, rebalance_days: rebalanceDays.value }) }) }

watch(() => route.path, (path) => {
  activeMode.value = path.endsWith('/formula-basket') ? 'formula' : 'alpha'
}, { immediate: true })
onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><RouterLink to="/app/more" class="muted small"><ArrowLeft :size="14" />返回更多工具</RouterLink><h1>{{ mode === 'formula' ? '公式系统与篮子计划' : 'Alpha、因子与 Walk-Forward' }}</h1><p>研究操作由人工触发并保留结果；AI、模型和公式都不能直接改变确定性策略动作或自动推送资格。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button></div>
    <div v-if="message" class="error-box" role="alert">{{ message }}</div>
    <section class="panel alpha-controls"><div class="panel-head"><div><h2>研究输入</h2><p>同一组代码、日期和模型参数贯穿分析 API，便于复现。</p></div><span class="tag warn">显式运行</span></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="alpha-code">主标的</label><input id="alpha-code" v-model="code" class="field-input" /></div><div class="field"><label for="alpha-model">模型</label><select id="alpha-model" v-model="modelType" class="field-select"><option value="lightgbm">LightGBM</option><option value="xgboost">XGBoost</option><option value="ensemble">Ensemble</option></select></div><div class="field"><label for="alpha-start">开始日期</label><input id="alpha-start" v-model="startDate" class="field-input" type="date" /></div><div class="field"><label for="alpha-end">结束日期</label><input id="alpha-end" v-model="endDate" class="field-input" type="date" /></div><div class="field"><label for="alpha-codes">因子分析标的</label><input id="alpha-codes" v-model="factorCodes" class="field-input" placeholder="逗号分隔" /></div><div class="field"><label for="alpha-cash">初始资金</label><input id="alpha-cash" v-model.number="initialCash" class="field-input" type="number" min="1" /></div></div></div></section>
    <nav class="workspace-tabs" aria-label="Alpha 工作区"><button v-for="item in [{ key: 'alpha', label: '模型与因子' }, { key: 'factor', label: '单因子' }, { key: 'formula', label: '公式' }, { key: 'basket', label: '篮子计划' }]" :key="item.key" type="button" :class="{ active: mode === item.key }" @click="activeMode = item.key as Mode">{{ item.label }}</button></nav>

    <template v-if="mode === 'alpha'">
      <section class="summary-strip"><div class="summary-item"><span>模型状态</span><strong>{{ modelStatus?.status || modelStatus?.model_status || '—' }}</strong><small>Alpha API</small></div><div class="summary-item"><span>因子目录</span><strong>{{ factors.length }}</strong><small>可用因子</small></div><div class="summary-item"><span>重要性结果</span><strong>{{ factorEval.length || '—' }}</strong><small>需要显式运行</small></div><div class="summary-item"><span>自动动作</span><strong>不允许</strong><small>研究结果不绕过门禁</small></div></section>
      <section class="panel"><div class="panel-head"><div><h2>模型操作</h2><p>预测、绩效、SHAP、Walk-Forward、模型比较和因子挖掘统一使用当前研究 API。</p></div><Beaker :size="19" class="faint" /></div><div class="panel-body"><div class="form-actions"><button class="button" :disabled="loading" @click="runPredict"><Play :size="15" />预测</button><button class="button" :disabled="loading" @click="runPerformance"><Play :size="15" />绩效回放</button><button class="button" :disabled="loading" @click="runShap"><Play :size="15" />SHAP</button><button class="button" :disabled="loading" @click="runWalkForward"><ShieldCheck :size="15" />Walk-Forward</button><button class="button" :disabled="loading" @click="runModelCompare"><Play :size="15" />模型比较</button><button class="button" :disabled="loading" @click="runFactorEval"><Play :size="15" />因子评价</button><button class="button" :disabled="loading" @click="runMine"><Play :size="15" />因子挖掘</button><button class="button" :disabled="loading" @click="runOptimize"><Play :size="15" />超参优化</button></div><div v-if="activeTask" class="empty">{{ activeTask }}运行中…</div></div></section>
      <section class="section-grid two alpha-result-grid"><section class="panel"><div class="panel-head"><div><h2>预测与绩效</h2><p>模型分数和模拟权益分开，不与决策报告混用。</p></div></div><div class="panel-body"><div v-if="!prediction && !performance" class="empty">先选择一个模型操作。</div><template v-else><div v-if="prediction" class="metric-grid"><div class="metric-cell"><span>AUC</span><strong>{{ numberValue(prediction.auc) }}</strong></div><div class="metric-cell"><span>准确率</span><strong>{{ numberValue(prediction.accuracy) }}</strong></div><div class="metric-cell"><span>预测条数</span><strong>{{ prediction.predictions?.length || 0 }}</strong></div></div><div v-if="performance" class="metric-grid" style="margin-top:12px"><div v-for="(item, key) in performance.metrics || performance.summary || {}" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ numberValue(item) }}</strong></div></div></template></div></section><section class="panel"><div class="panel-head"><div><h2>因子挖掘与重要性</h2><p>输出是候选研究材料，不是已晋级策略。</p></div></div><div class="panel-body"><div v-if="!mined.length && !factorEval.length" class="empty">暂无因子结果。</div><div v-else class="table-scroll"><table class="decision-table"><thead><tr><th>因子</th><th>IC</th><th>|IC|</th><th>换手</th></tr></thead><tbody><tr v-for="row in (mined.length ? mined : factorEval).slice(0, 30)" :key="row.name || row.factor"><td>{{ row.name || row.factor }}</td><td>{{ numberValue(row.ic) }}</td><td>{{ numberValue(row.abs_ic) }}</td><td>{{ numberValue(row.turnover) }}</td></tr></tbody></table></div></div></section></section>
      <section class="section-grid two"><section class="panel"><div class="panel-head"><div><h2>Walk-Forward 稳定性</h2><p>窗口级结果和稳定性由后端返回。</p></div></div><div class="panel-body"><div v-if="!walkForward" class="empty">暂无 Walk-Forward 结果。</div><template v-else><div class="metric-grid"><div v-for="(item, key) in walkForward.stability || {}" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ typeof item === 'boolean' ? (item ? '是' : '否') : numberValue(item) }}</strong></div></div><div class="table-scroll" style="margin-top:14px"><table class="decision-table"><thead><tr><th>窗口</th><th>训练 AUC</th><th>测试 AUC</th><th>差值</th></tr></thead><tbody><tr v-for="row in walkForward.windows || []" :key="row.window"><td>{{ row.window }}</td><td>{{ numberValue(row.train_auc) }}</td><td>{{ numberValue(row.test_auc) }}</td><td>{{ numberValue(row.gap) }}</td></tr></tbody></table></div></template></div></section><section class="panel"><div class="panel-head"><div><h2>模型 / SHAP</h2><p>SHAP 不可用时明确显示原因，不以空图替代。</p></div></div><div class="panel-body"><pre v-if="shap || modelComparison || optimization" class="result-code">{{ json(shap || modelComparison || optimization) }}</pre><div v-else class="empty">暂无解释或优化结果。</div></div></section></section>
    </template>

    <template v-else-if="mode === 'factor'">
      <section class="panel"><div class="panel-head"><div><h2>单因子与相关性</h2><p>选择因子后可运行 IC、分层收益、相关性和衰减分析。</p></div><select v-model="factorName" class="field-select"><option v-for="item in factors" :key="String(item.name)" :value="String(item.name)">{{ item.label || item.name }}</option></select></div><div class="panel-body"><div class="form-actions"><button class="button primary" :disabled="loading || !factorName" @click="runFactorAnalyze"><Play :size="15" />运行单因子</button><button class="button" :disabled="loading" @click="runCorrelation"><Play :size="15" />相关性</button><button class="button" :disabled="loading" @click="runDecay"><Play :size="15" />因子衰减</button></div><section class="section-grid two" style="margin-top:18px"><section class="panel nested-panel"><div class="panel-head"><h3>IC 与分层收益</h3></div><div class="panel-body"><div v-if="!factorAnalysis" class="empty">暂无单因子结果。</div><div v-else class="metric-grid"><div v-for="(item, key) in factorAnalysis" :key="String(key)" class="metric-cell"><span>{{ key }}</span><strong>{{ typeof item === 'number' ? numberValue(item) : Array.isArray(item) ? `${item.length} 项` : String(item ?? '—') }}</strong></div></div></div></section><section class="panel nested-panel"><div class="panel-head"><h3>相关性 / 衰减</h3></div><div class="panel-body"><pre v-if="factorCorrelation || factorDecay" class="result-code">{{ json(factorCorrelation || factorDecay) }}</pre><div v-else class="empty">暂无结果。</div></div></section></section></div></section>
    </template>

    <template v-else-if="mode === 'formula'">
      <section class="panel"><div class="panel-head"><div><h2>公式执行</h2><p>公式解释器和全市场筛选结果仅用于研究，输入和错误都保留在当前页面。</p></div></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="formula-source">公式</label><textarea id="formula-source" v-model="formula" class="field-input" rows="3" /></div><div class="field"><label>目录</label><div class="formula-catalog"><span v-for="item in formulas.slice(0, 12)" :key="item.name || item.function" class="tag">{{ item.name || item.function }}</span></div></div></div><div class="form-actions"><button class="button primary" :disabled="loading" @click="evaluateFormula"><Play :size="15" />评估当前标的</button><button class="button" :disabled="loading" @click="screenFormula"><Play :size="15" />筛选候选</button></div><div class="section-grid two" style="margin-top:18px"><section class="panel nested-panel"><div class="panel-head"><h3>评估结果</h3></div><div class="panel-body"><div v-if="!formulaResult" class="empty">暂无评估结果。</div><pre v-else class="result-code">{{ json(formulaResult) }}</pre></div></section><section class="panel nested-panel"><div class="panel-head"><h3>筛选结果</h3></div><div class="panel-body"><div v-if="!formulaScreenResult" class="empty">暂无筛选结果。</div><pre v-else class="result-code">{{ json(formulaScreenResult) }}</pre></div></section></div></div></section>
    </template>

    <template v-else>
      <section class="panel"><div class="panel-head"><div><h2>候选篮子计划</h2><p>候选、分配、再平衡和资金参数显式提交；计划不会产生真实订单。</p></div><ShieldCheck :size="19" class="faint" /></div><div class="panel-body"><div class="field-grid"><div class="field"><label for="basket-candidates">候选 JSON</label><textarea id="basket-candidates" v-model="basketCandidates" class="field-input" rows="8" /></div><div class="stack"><div class="field"><label for="basket-allocation">分配方式</label><select id="basket-allocation" v-model="allocation" class="field-select"><option value="equal">等权</option><option value="probability">按概率</option><option value="score">按分数</option></select></div><div class="field"><label for="basket-rebalance">再平衡周期</label><input id="basket-rebalance" v-model.number="rebalanceDays" class="field-input" type="number" min="1" /></div></div></div><div class="form-actions"><button class="button primary" :disabled="loading" @click="planBasket"><Play :size="15" />生成计划</button><button class="button" :disabled="loading" @click="backtestBasket"><Play :size="15" />篮子回测</button></div><div class="section-grid two" style="margin-top:18px"><section class="panel nested-panel"><div class="panel-head"><h3>计划</h3></div><div class="panel-body"><div v-if="!basketPlan" class="empty">暂无篮子计划。</div><pre v-else class="result-code">{{ json(basketPlan) }}</pre></div></section><section class="panel nested-panel"><div class="panel-head"><h3>回测</h3></div><div class="panel-body"><div v-if="!basketResult" class="empty">暂无篮子回测。</div><pre v-else class="result-code">{{ json(basketResult) }}</pre></div></section></div></div></section>
    </template>
  </section>
</template>
