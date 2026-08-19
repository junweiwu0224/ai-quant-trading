<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  ArrowLeft,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Code2,
  Database,
  FileSearch,
  FlaskConical,
  Gauge,
  Layers3,
  ListChecks,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
  WandSparkles,
  X,
} from 'lucide-vue-next'
import { api, isAbortError, type AIArtifactRequest, type AIChatMessage, type AIContextSnapshot, type AIEvent, type AIProviderChannel, type AIProviderAttempt, type AIReport, type AIReportRecord, type AISession, type AISkillInfo, type AITask, type AIChannelInput, type RunFlowEvent, type RunFlowNode, type RunFlowSnapshot } from '../api/client'
import { useAppStore } from '../stores/app'
import type { DecisionResearch } from '../types'

type WorkbenchTab = 'chat' | 'research' | 'tasks' | 'reports' | 'settings'

type QuickSkill = {
  id: string
  kind: string
  profile: string
  name: string
  description: string
  icon: typeof BrainCircuit
  run: (payload: AIArtifactRequest) => Promise<{ task: AITask; execution?: string }>
}

const store = useAppStore()
const route = useRoute()
const activeTab = ref<WorkbenchTab>('chat')
const loading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const status = ref<Record<string, unknown> | null>(null)
const channels = ref<AIProviderChannel[]>([])
const models = ref<Record<string, unknown>[]>([])
const skills = ref<AISkillInfo[]>([])

const sessions = ref<AISession[]>([])
const activeSession = ref<AISession | null>(null)
const activeSessionId = ref('')
const selectedSkillIds = ref<string[]>([])
const sessionLoading = ref(false)
const sessionDeleting = ref(false)
const composer = ref('')
const chatSending = ref(false)
const chatError = ref('')
const chatProgress = ref('')
let chatController: AbortController | null = null

const snapshot = ref<AIContextSnapshot>({
  market: 'CN',
  instrument: '600519',
  symbol: '600519',
  as_of: '',
  blocks: {},
  evidence: [],
  quality_status: 'unknown',
  source: 'provided_snapshot',
})
const snapshotText = ref(JSON.stringify(snapshot.value, null, 2))
const snapshotSymbol = ref('600519')
const snapshotLoading = ref(false)
const snapshotError = ref('')
const snapshotDirty = ref(false)

const taskKind = ref('analysis')
const taskProfile = ref('standard')
const taskQuestion = ref('')
const taskRequestText = ref('{}')
const taskSubmitting = ref(false)
const taskMessage = ref('')
const tasks = ref<AITask[]>([])
const activeTask = ref<AITask | null>(null)
const activeTaskId = ref('')
const taskEvents = ref<AIEvent[]>([])
const taskLoading = ref(false)
const activeFlow = ref<RunFlowSnapshot | null>(null)
const flowLoading = ref(false)
const flowEventFilter = ref('all')
const flowEventSearch = ref('')
const selectedFlowNodeId = ref('')
let taskPollTimer: number | undefined

const reports = ref<AIReportRecord[]>([])
const selectedReport = ref<AIReportRecord | null>(null)
const reportLoading = ref(false)

const legacyAgents = ref<Record<string, unknown>[]>([])
const legacyOperations = ref<Record<string, unknown>[]>([])
const legacyResearch = ref<Record<string, unknown>[]>([])

const providerEditingId = ref('')
const providerSaving = ref(false)
const providerForm = ref<AIChannelInput>({
  id: '',
  name: '',
  protocol: 'openai_compatible',
  base_url: '',
  model: '',
  secret_ref: '',
  command: [],
  enabled: true,
  priority: 100,
  timeout_seconds: 45,
  supports_json: true,
  supports_stream: true,
})

const quickSkills: QuickSkill[] = [
  {
    id: 'deep_research',
    kind: 'research',
    profile: 'research',
    name: '深度研究',
    description: '围绕冻结快照拆分问题，整理证据、未知项和下一步核验。',
    icon: Search,
    run: (payload) => api.aiResearch(payload),
  },
  {
    id: 'screening_query',
    kind: 'screening',
    profile: 'quick',
    name: '自然语言选股',
    description: '把一句话转换成可审阅的筛选条件，不直接执行筛选。',
    icon: ListChecks,
    run: (payload) => api.aiScreening(payload),
  },
  {
    id: 'prediction_interpretation',
    kind: 'interpretation',
    profile: 'explain',
    name: '预测与因子解读',
    description: '解释预测值、因子贡献和样本限制，不补造预测结果。',
    icon: Gauge,
    run: (payload) => api.aiInterpret(payload),
  },
  {
    id: 'strategy_generation',
    kind: 'strategy',
    profile: 'research',
    name: '策略草案',
    description: '生成规则和验证计划，必须经过验证才能进入策略工作流。',
    icon: WandSparkles,
    run: (payload) => api.aiStrategy(payload),
  },
  {
    id: 'backtest_diagnosis',
    kind: 'diagnosis',
    profile: 'explain',
    name: '回测诊断',
    description: '识别数据、成本、过拟合和执行风险，不伪造指标。',
    icon: FlaskConical,
    run: (payload) => api.aiDiagnose(payload),
  },
  {
    id: 'report_analysis',
    kind: 'report_analysis',
    profile: 'research',
    name: '研报解读',
    description: '整理研报中的观点、证据、风险和待核验问题。',
    icon: FileSearch,
    run: (payload) => api.aiReportAnalysis(payload),
  },
]

const availableSkills = computed(() => skills.value.length ? skills.value : quickSkills.map((item) => ({ id: item.id, name: item.name, description: item.description })))
const selectedSkillNames = computed(() => availableSkills.value.filter((item) => selectedSkillIds.value.includes(item.id)).map((item) => item.name || item.id))
const messageList = computed<AIChatMessage[]>(() => activeSession.value?.messages || [])
const workerState = computed(() => {
  const value = status.value?.worker
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})
const providerReady = computed(() => channels.value.some((channel) => channel.enabled !== false && channel.readiness?.ready === true))
const providerStateLabel = computed(() => {
  if (providerReady.value) return 'provider 已真实验证'
  if (channels.value.some((channel) => channel.readiness?.overall === 'configured_recent_failure')) return 'provider 最近调用失败'
  if (channels.value.some((channel) => channel.readiness?.overall === 'configured_unverified')) return 'provider 已配置，尚未联调'
  return '等待 provider 配置'
})
const reportBody = computed<AIReport>(() => selectedReport.value?.body || {})
const reportOpinions = computed(() => Array.isArray(reportBody.value.opinions) ? reportBody.value.opinions : [])
const reportSynthesis = computed(() => reportBody.value.synthesis && typeof reportBody.value.synthesis === 'object' ? reportBody.value.synthesis : null)
const reportLimitations = computed(() => stringList(reportBody.value.limitations))
const flowLanes = computed(() => [...(activeFlow.value?.lanes || [])].sort((left, right) => left.order - right.order))
const flowEvents = computed<RunFlowEvent[]>(() => activeFlow.value?.events || [])
const flowNodes = computed<RunFlowNode[]>(() => activeFlow.value?.nodes || [])
const selectedFlowNode = computed(() => flowNodes.value.find((node) => node.id === selectedFlowNodeId.value) || null)
const filteredFlowEvents = computed(() => {
  const query = flowEventSearch.value.trim().toLowerCase()
  return flowEvents.value.filter((event) => {
    const severityMatch = flowEventFilter.value === 'all' || event.severity === flowEventFilter.value
    const haystack = `${event.title} ${event.message || ''} ${event.type}`.toLowerCase()
    return severityMatch && (!query || haystack.includes(query))
  })
})
const capabilityRows = computed<Array<Record<string, any> & { id: string }>>(() => {
  const matrix = record(status.value?.capability_matrix)
  return Object.entries(matrix).map(([id, value]) => ({ id, ...record(value) }))
})
const providerAttempts = computed<AIProviderAttempt[]>(() => channels.value
  .flatMap((channel) => Array.isArray(channel.attempts) ? channel.attempts.map((attempt) => ({ ...attempt, provider: attempt.provider || channel.id })) : [])
  .sort((left, right) => Number(right.recorded_at || 0) - Number(left.recorded_at || 0))
  .slice(0, 16))
const reportDsaBlocks = computed(() => {
  const body = record(reportBody.value)
  const definitions = [
    ['core_conclusion', '核心结论'],
    ['data_perspective', '数据视角'],
    ['intelligence', '情报与舆情'],
    ['battle_plan', '复核计划'],
    ['phase_decision', '阶段判断'],
    ['signal_attribution', '信号归因'],
    ['agent_disagreement_explanation', 'Agent 分歧解释'],
  ] as const
  return definitions.map(([key, title]) => ({ key, title, value: record(body[key]) })).filter((item) => Object.keys(item.value).length > 0)
})

function record(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

function shortText(value: unknown, fallback = '—'): string {
  const text = String(value ?? '').trim()
  return text || fallback
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return '{}'
  }
}

function formatTime(value: unknown): string {
  const text = String(value || '')
  if (!text) return '—'
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN', { hour12: false })
}

function taskStatusClass(value: unknown): string {
  const statusValue = String(value || '')
  if (['completed', 'degraded'].includes(statusValue)) return statusValue === 'completed' ? 'good' : 'warn'
  if (['failed', 'cancelled'].includes(statusValue)) return 'bad'
  return 'warn'
}

function taskStatusLabel(value: unknown): string {
  return ({ queued: '排队中', running: '运行中', completed: '已完成', degraded: '已降级', failed: '失败', cancel_requested: '取消中', cancelled: '已取消' } as Record<string, string>)[String(value || '')] || shortText(value)
}

function flowStatusClass(value: unknown): string {
  const statusValue = String(value || '')
  if (['success', 'complete'].includes(statusValue)) return 'good'
  if (['failed', 'danger'].includes(statusValue)) return 'bad'
  if (['degraded', 'fallback', 'retry', 'warning'].includes(statusValue)) return 'warn'
  return 'muted'
}

function flowStatusLabel(value: unknown): string {
  return ({ pending: '等待', running: '运行中', success: '成功', failed: '失败', degraded: '降级', fallback: '已降级', retry: '重试', skipped: '跳过', cancelled: '已取消', unknown: '未知' } as Record<string, string>)[String(value || '')] || shortText(value)
}

function flowNodesForLane(laneId: string): RunFlowNode[] {
  return flowNodes.value.filter((node) => node.lane === laneId)
}

function flowNodeLabel(nodeId: unknown): string {
  return shortText(flowNodes.value.find((node) => node.id === nodeId)?.label, String(nodeId || '未知节点'))
}

function formatDuration(value: unknown): string {
  const duration = Number(value)
  if (!Number.isFinite(duration) || duration < 0) return '—'
  const seconds = (duration / 1000).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1, useGrouping: false })
  return duration >= 1000 ? `${seconds}s` : `${Math.round(duration)}ms`
}

function readinessLabel(value: unknown): string {
  return ({ verified: '已真实验证', ready: '已真实验证', configured_unverified: '已配置，尚未联调', configured_recent_failure: '最近调用失败', needs_configuration: '待配置', unavailable: '不可用', disabled: '已停用', not_checked: '未检查' } as Record<string, string>)[String(value || '')] || shortText(value, '未检查')
}

function readinessClass(value: unknown): string {
  const state = String(value || '')
  if (['verified', 'ready'].includes(state)) return 'good'
  if (state === 'configured_recent_failure') return 'bad'
  return 'warn'
}

function capabilityState(value: unknown): string {
  return value === true ? '支持' : value === false ? '不支持' : '—'
}

function dsaText(value: unknown, fallback = '暂无记录'): string {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function dsaList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => dsaText(item, '')).filter(Boolean).slice(0, 20) : []
}

function dsaPercent(value: unknown): string {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${Math.round(number)}%`
}

function dsaValue(block: Record<string, any>, key: string): Record<string, any> {
  return record(block[key])
}

function eventLabel(event: AIEvent): string {
  const type = String(event.event_type || event.type || '')
  return ({ accepted: '任务已接收', task_created: '创建任务', task_started: 'Worker 开始', thinking: '整理冻结输入', stage_start: '角色编排', stage_done: '阶段完成', provider_start: '调用 provider', provider_done: 'provider 返回', provider_error: 'provider 错误', generating: '生成综合报告', tool_start: '技能开始', tool_done: '技能完成', research_plan: '研究计划', research_done: '研究完成', done: '任务完成', error: '任务错误', cancelled: '任务取消' } as Record<string, string>)[type] || type || '事件'
}

function eventDetail(event: AIEvent): string {
  const payload = record(event.payload)
  return shortText(payload.message || payload.stage || payload.skill || payload.code || payload.status || event.message, '已记录')
}

function syncSnapshotText(next: AIContextSnapshot) {
  snapshot.value = next
  snapshotText.value = prettyJson(next)
  snapshotDirty.value = false
}

function applySnapshotText() {
  snapshotError.value = ''
  try {
    const parsed = JSON.parse(snapshotText.value)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('冻结上下文必须是 JSON 对象')
    const next = { ...record(parsed), market: String(record(parsed).market || store.market).toUpperCase(), instrument: String(record(parsed).instrument || record(parsed).symbol || '').trim(), source: String(record(parsed).source || 'provided_snapshot') } as AIContextSnapshot
    if (!next.instrument) throw new Error('冻结上下文需要 instrument 或 symbol')
    syncSnapshotText(next)
    noticeMessage.value = '冻结上下文已更新；后续任务只会使用这份快照。'
  } catch (reason) {
    snapshotError.value = reason instanceof Error ? reason.message : '冻结上下文 JSON 无法解析'
  }
}

async function loadResearchSnapshot() {
  const symbol = snapshotSymbol.value.trim()
  if (!symbol) {
    snapshotError.value = '请输入股票代码或标的代码'
    return
  }
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const [quoteResult, researchResult] = await Promise.allSettled([
      api.stockQuote(symbol, store.market),
      api.decisionResearch(store.market, symbol),
    ])
    const quote = quoteResult.status === 'fulfilled' ? quoteResult.value : { status: 'failed', error: 'quote_unavailable' }
    const research: DecisionResearch = researchResult.status === 'fulfilled' ? researchResult.value : { symbol, status: 'failed', bars: [], source: 'none', authoritative: false, fallback_reason: 'decision_research_unavailable' }
    const bars = Array.isArray(research.bars) ? research.bars : []
    const authoritative = research.authoritative !== false && research.source !== 'external_kline_fallback'
    const historyStatus = bars.length ? (authoritative ? 'available' : 'degraded') : 'partial'
    const next: AIContextSnapshot = {
      market: store.market,
      instrument: symbol,
      symbol,
      as_of: new Date().toISOString(),
      blocks: {
        quote: { status: quoteResult.status === 'fulfilled' ? 'available' : 'failed', ...record(quote) },
        price_history: { status: historyStatus, source: research.source || 'unknown', authoritative, bars: bars.slice(-120) },
        research_status: research.status,
        research_quality: { ...record(research.data_quality), source: research.source || 'unknown', authoritative, fallback_reason: research.fallback_reason || '' },
      },
      evidence: [
        { source: 'stock_quote', claim: quoteResult.status === 'fulfilled' ? '调用方加载了行情快照' : '行情快照不可用' },
        { source: 'decision_research', claim: bars.length ? `加载 ${bars.length} 条历史 K 线（${research.source || '未知来源'}）` : '历史 K 线不足' },
        ...(authoritative ? [] : [{ source: 'decision_research', claim: '当前行情不是确定性决策权威输入，仅可用于人工研究复核' }]),
      ],
      quality_status: quoteResult.status === 'fulfilled' && bars.length ? (authoritative ? 'available' : 'degraded') : 'partial',
      source: authoritative ? 'vue_research_snapshot' : 'vue_research_snapshot:external_fallback',
      authoritative,
      manual_research_only: !authoritative,
      latest_date: research.latest_date || bars.at(-1)?.date || null,
      updated_at: research.updated_at || null,
      fallback_reason: research.fallback_reason || '',
    }
    syncSnapshotText(next)
    snapshotSymbol.value = symbol
    noticeMessage.value = `已冻结 ${store.market} / ${symbol} 的研究输入。`
  } catch (reason) {
    snapshotError.value = reason instanceof Error ? reason.message : '研究快照加载失败'
  } finally {
    snapshotLoading.value = false
  }
}

async function loadSession(sessionId: string) {
  if (!sessionId) return
  sessionLoading.value = true
  chatError.value = ''
  try {
    const detail = await api.aiSession(sessionId)
    activeSessionId.value = sessionId
    activeSession.value = detail
    selectedSkillIds.value = Array.isArray(detail.skills) ? [...detail.skills] : []
    await nextTick()
    const messageViewport = document.querySelector('.ai-message-list')
    if (messageViewport instanceof HTMLElement) messageViewport.scrollTop = messageViewport.scrollHeight
  } catch (reason) {
    chatError.value = reason instanceof Error ? reason.message : '会话加载失败'
  } finally {
    sessionLoading.value = false
  }
}

async function loadSessions() {
  try {
    const response = await api.aiSessions(100)
    sessions.value = response.items || []
    if (activeSessionId.value && sessions.value.some((item) => item.id === activeSessionId.value)) {
      await loadSession(activeSessionId.value)
    } else if (sessions.value[0]) {
      await loadSession(sessions.value[0].id)
    }
  } catch (reason) {
    chatError.value = reason instanceof Error ? reason.message : '会话列表加载失败'
  }
}

async function newSession() {
  chatError.value = ''
  try {
    const created = await api.createAiSession({ title: '新对话', skills: selectedSkillIds.value })
    sessions.value = [created, ...sessions.value.filter((item) => item.id !== created.id)]
    activeSessionId.value = created.id
    activeSession.value = created
    composer.value = ''
    noticeMessage.value = '已创建新会话。'
  } catch (reason) {
    chatError.value = reason instanceof Error ? reason.message : '新建会话失败'
  }
}

async function ensureSession(firstMessage: string): Promise<AISession> {
  if (activeSession.value) return activeSession.value
  const created = await api.createAiSession({ title: firstMessage.slice(0, 36) || '新对话', skills: selectedSkillIds.value })
  sessions.value = [created, ...sessions.value]
  activeSession.value = created
  activeSessionId.value = created.id
  return created
}

async function toggleSkill(skillId: string) {
  const next = selectedSkillIds.value.includes(skillId)
    ? selectedSkillIds.value.filter((item) => item !== skillId)
    : [...selectedSkillIds.value, skillId]
  selectedSkillIds.value = next
  if (activeSession.value) {
    try {
      const updated = await api.updateAiSession(activeSession.value.id, { title: activeSession.value.title, skills: next })
      activeSession.value = updated
      sessions.value = sessions.value.map((item) => item.id === updated.id ? { ...item, skills: updated.skills, updated_at: updated.updated_at } : item)
    } catch (reason) {
      chatError.value = reason instanceof Error ? reason.message : '技能偏好保存失败'
    }
  }
}

async function deleteActiveSession(session: AISession) {
  if (sessionDeleting.value) return
  sessionDeleting.value = true
  try {
    await api.deleteAiSession(session.id)
    sessions.value = sessions.value.filter((item) => item.id !== session.id)
    if (activeSessionId.value === session.id) {
      activeSession.value = null
      activeSessionId.value = ''
      selectedSkillIds.value = []
      if (sessions.value[0]) await loadSession(sessions.value[0].id)
    }
    noticeMessage.value = '会话已删除。'
  } catch (reason) {
    chatError.value = reason instanceof Error ? reason.message : '删除会话失败'
  } finally {
    sessionDeleting.value = false
  }
}

async function sendChat() {
  const message = composer.value.trim()
  if (!message || chatSending.value) return
  composer.value = ''
  chatSending.value = true
  chatError.value = ''
  chatProgress.value = '准备冻结上下文'
  chatController?.abort()
  chatController = new AbortController()
  try {
    const session = await ensureSession(message)
    const result = await api.aiChatStream(
      { session_id: session.id, message, context: snapshot.value, skills: selectedSkillIds.value },
      {
        signal: chatController.signal,
        onEvent: async (event) => {
          const type = String(event.type || event.event_type || '')
          if (type === 'thinking' || type === 'chat_accepted') chatProgress.value = shortText(event.message || record(event.payload).message, '处理中')
          if (type === 'error') chatProgress.value = shortText(event.message || event.error || record(event.payload).message, 'AI provider 返回错误')
        },
      },
    )
    if (result.terminal === 'error') throw new Error(shortText(result.error, 'AI 对话失败'))
    await loadSession(session.id)
    sessions.value = [activeSession.value as AISession, ...sessions.value.filter((item) => item.id !== session.id)]
  } catch (reason) {
    if (!isAbortError(reason)) chatError.value = reason instanceof Error ? reason.message : 'AI 对话失败'
  } finally {
    chatSending.value = false
    chatProgress.value = ''
    chatController = null
  }
}

function stopChat() {
  chatController?.abort()
  chatSending.value = false
  chatProgress.value = ''
}

function buildTaskRequest(): Record<string, unknown> {
  let request: Record<string, unknown> = {}
  try {
    const parsed = JSON.parse(taskRequestText.value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) request = parsed
  } catch {
    throw new Error('任务请求 JSON 无法解析')
  }
  if (taskQuestion.value.trim()) {
    request = { ...request, question: taskQuestion.value.trim(), query: taskQuestion.value.trim() }
  }
  return request
}

async function submitTask(runNow = false) {
  taskSubmitting.value = true
  taskMessage.value = ''
  try {
    const request = buildTaskRequest()
    const response = await api.createAiTask({ kind: taskKind.value, profile: taskProfile.value, request, context: snapshot.value, run_now: runNow })
    activeTask.value = response.task
    activeTaskId.value = response.task.id
    taskMessage.value = runNow ? '任务已在当前进程运行。' : '任务已提交到独立 Pi Agent Worker 队列。'
    activeTab.value = 'tasks'
    await loadTasks()
    await loadTask(response.task.id)
    startTaskPolling()
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '任务提交失败'
  } finally {
    taskSubmitting.value = false
  }
}

async function runQuickSkill(skill: QuickSkill) {
  taskMessage.value = ''
  taskSubmitting.value = true
  try {
    const response = await skill.run({ context: snapshot.value, query: taskQuestion.value.trim(), question: taskQuestion.value.trim() })
    activeTask.value = response.task
    activeTaskId.value = response.task.id
    taskKind.value = skill.kind
    taskProfile.value = skill.profile
    taskMessage.value = response.execution === 'inline' ? `${skill.name} 已完成当前进程运行。` : `${skill.name} 已提交。`
    activeTab.value = 'tasks'
    await loadTasks()
    await loadTask(response.task.id)
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : `${skill.name} 运行失败`
  } finally {
    taskSubmitting.value = false
  }
}

async function loadTasks() {
  try {
    const response = await api.aiTasks({ limit: 100 })
    tasks.value = response.items || []
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '任务列表加载失败'
  }
}

async function loadTask(taskId: string) {
  if (!taskId) return
  taskLoading.value = true
  flowLoading.value = true
  try {
    const [detail, eventResponse, flow] = await Promise.all([
      api.aiTask(taskId),
      api.aiTaskEvents(taskId),
      api.aiTaskFlow(taskId).catch(() => null),
    ])
    activeTask.value = detail
    activeTaskId.value = taskId
    taskEvents.value = eventResponse.items || []
    activeFlow.value = flow
    selectedFlowNodeId.value = flow?.nodes?.[0]?.id || ''
    if (detail.report_id) await loadReport(String(detail.report_id))
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '任务详情加载失败'
  } finally {
    taskLoading.value = false
    flowLoading.value = false
  }
}

async function runActiveTask() {
  if (!activeTask.value) return
  taskMessage.value = ''
  try {
    const detail = await api.runAiTask(activeTask.value.id)
    activeTask.value = detail
    await loadTask(detail.id)
    startTaskPolling()
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '任务运行失败'
  }
}

async function cancelActiveTask() {
  if (!activeTask.value) return
  try {
    activeTask.value = await api.cancelAiTask(activeTask.value.id)
    await loadTask(activeTask.value.id)
    stopTaskPolling()
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '任务取消失败'
  }
}

function startTaskPolling() {
  stopTaskPolling()
  if (!activeTask.value || ['completed', 'degraded', 'failed', 'cancelled'].includes(String(activeTask.value.status))) return
  taskPollTimer = window.setInterval(async () => {
    if (activeTaskId.value) await loadTask(activeTaskId.value)
    if (activeTask.value && ['completed', 'degraded', 'failed', 'cancelled'].includes(String(activeTask.value.status))) stopTaskPolling()
  }, 2500)
}

function stopTaskPolling() {
  if (taskPollTimer !== undefined) window.clearInterval(taskPollTimer)
  taskPollTimer = undefined
}

async function loadReports() {
  reportLoading.value = true
  try {
    const response = await api.aiReports(100)
    reports.value = response.items || []
    if (selectedReport.value && reports.value.some((item) => item.id === selectedReport.value?.id)) {
      await loadReport(String(selectedReport.value.id))
    } else if (reports.value[0]) {
      await loadReport(String(reports.value[0].id))
    }
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '报告列表加载失败'
  } finally {
    reportLoading.value = false
  }
}

async function loadReport(reportId: string) {
  if (!reportId) return
  try {
    const [reportResult, flowResult] = await Promise.allSettled([api.aiReport(reportId), api.aiReportFlow(reportId)])
    if (reportResult.status === 'rejected') throw reportResult.reason
    selectedReport.value = reportResult.value
    if (flowResult.status === 'fulfilled') {
      activeFlow.value = flowResult.value
      selectedFlowNodeId.value = flowResult.value.nodes?.[0]?.id || ''
    }
  } catch (reason) {
    taskMessage.value = reason instanceof Error ? reason.message : '报告加载失败'
  }
}

function resetProviderForm() {
  providerEditingId.value = ''
  providerForm.value = { id: '', name: '', protocol: 'openai_compatible', base_url: '', model: '', secret_ref: '', command: [], enabled: true, priority: 100, timeout_seconds: 45, supports_json: true, supports_stream: true }
}

function editProvider(channel: AIProviderChannel) {
  providerEditingId.value = channel.id
  providerForm.value = {
    id: channel.id,
    name: channel.name,
    protocol: channel.protocol || 'openai_compatible',
    base_url: channel.base_url || '',
    model: channel.model || '',
    secret_ref: channel.secret_ref || '',
    command: Array.isArray(channel.command) ? channel.command.map(String) : [],
    enabled: channel.enabled !== false,
    priority: Number(channel.priority || 100),
    timeout_seconds: Number(channel.timeout_seconds || 45),
    supports_json: channel.supports_json !== false,
    supports_stream: channel.supports_stream !== false,
  }
}

async function saveProvider() {
  providerSaving.value = true
  try {
    const response = await api.saveAiChannel(providerForm.value, providerEditingId.value || undefined)
    channels.value = response.items || []
    resetProviderForm()
    status.value = await api.aiStatus()
    noticeMessage.value = 'provider 配置已保存；数据库只保存 secret_ref，不保存密钥正文。'
  } catch (reason) {
    errorMessage.value = reason instanceof Error ? reason.message : 'provider 配置保存失败'
  } finally {
    providerSaving.value = false
  }
}

async function loadLegacyCompatibility() {
  const [agentResponse, operationResponse, researchResponse] = await Promise.all([
    api.get<Record<string, unknown>>('/api/agentic/agents').catch(() => ({})),
    api.get<Record<string, unknown>>('/api/agentic/operations?limit=20').catch(() => ({})),
    api.get<Record<string, unknown>>('/api/agentic/research?limit=10').catch(() => ({})),
  ])
  const agents = record(agentResponse)
  const operations = record(operationResponse)
  const research = record(researchResponse)
  legacyAgents.value = Array.isArray(agents.agents) ? agents.agents as Record<string, unknown>[] : []
  legacyOperations.value = Array.isArray(operations.operations) ? operations.operations as Record<string, unknown>[] : []
  legacyResearch.value = Array.isArray(research.research) ? research.research as Record<string, unknown>[] : []
}

async function refreshWorkbench() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [statusResponse, channelResponse, modelResponse, skillResponse] = await Promise.all([
      api.aiStatus(),
      api.aiChannels(),
      api.aiModels(),
      api.aiSkills(),
    ])
    status.value = statusResponse as Record<string, unknown>
    channels.value = channelResponse.items || []
    models.value = (modelResponse.items || []) as Record<string, unknown>[]
    skills.value = skillResponse.items || []
    await Promise.all([loadSessions(), loadTasks(), loadReports(), loadLegacyCompatibility()])
  } catch (reason) {
    errorMessage.value = reason instanceof Error ? reason.message : 'AI 工作台加载失败'
  } finally {
    loading.value = false
  }
}

function selectTask(task: AITask) {
  activeTab.value = 'tasks'
  void loadTask(task.id)
  startTaskPolling()
}

function chooseReport(report: AIReportRecord) {
  activeTab.value = 'reports'
  selectedReport.value = report
  if (report.id) void loadReport(String(report.id))
}

function setQuickTask(skill: QuickSkill) {
  taskKind.value = skill.kind
  taskProfile.value = skill.profile
  if (!taskQuestion.value) taskQuestion.value = skill.name === '自然语言选股' ? '筛选趋势稳定、风险可解释的标的' : `请对 ${snapshot.value.instrument || '当前标的'} 做${skill.name}`
  activeTab.value = 'research'
}

function statusValue(key: string, fallback = '—'): string {
  return shortText(status.value?.[key], fallback)
}

watch(() => store.market, (market) => {
  if (!snapshotDirty.value && snapshot.value.source === 'provided_snapshot') {
    syncSnapshotText({ ...snapshot.value, market })
  }
})

onMounted(() => {
  const queryTab = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab
  const querySymbol = Array.isArray(route.query.symbol) ? route.query.symbol[0] : route.query.symbol
  const queryPrompt = Array.isArray(route.query.prompt) ? route.query.prompt[0] : route.query.prompt
  if (['chat', 'research', 'tasks', 'reports', 'settings'].includes(String(queryTab))) activeTab.value = String(queryTab) as WorkbenchTab
  if (querySymbol) {
    snapshotSymbol.value = String(querySymbol)
    snapshot.value.instrument = String(querySymbol)
    snapshot.value.symbol = String(querySymbol)
  }
  if (queryPrompt) {
    composer.value = String(queryPrompt)
    taskQuestion.value = String(queryPrompt)
  }
  snapshot.value.market = store.market
  snapshotText.value = prettyJson(snapshot.value)
  void refreshWorkbench()
})

onBeforeUnmount(() => {
  chatController?.abort()
  stopTaskPolling()
})
</script>

<template>
  <section class="ai-workbench">
    <div class="page-head">
      <div>
        <RouterLink to="/app/research" class="muted small ai-back-link"><ArrowLeft :size="14" />研究工作区</RouterLink>
        <h1>AI 研究工作台</h1>
        <p>吸收参考项目的多角色对话、技能选择、冻结上下文和结构化报告流程。AI 只生成研究 artifact，不拥有决策、推送资格或订单权限。</p>
      </div>
      <div class="head-actions">
        <span class="tag" :class="providerReady ? 'good' : channels.some((channel) => channel.readiness?.overall === 'configured_recent_failure') ? 'bad' : 'warn'"><span class="status-dot" :class="providerReady ? 'good' : 'muted'" />{{ providerStateLabel }}</span>
        <button class="button" type="button" :disabled="loading" @click="refreshWorkbench"><RefreshCw :size="15" :class="{ spin: loading }" />刷新状态</button>
      </div>
    </div>

    <div v-if="errorMessage" class="error-box" role="alert"><CircleAlert :size="17" />{{ errorMessage }}</div>
    <div v-if="noticeMessage" class="ai-notice" role="status"><CheckCircle2 :size="17" />{{ noticeMessage }}<button class="icon-button compact-icon" type="button" title="关闭提示" aria-label="关闭提示" @click="noticeMessage = ''"><X :size="14" /></button></div>

    <section class="panel ai-boundary-panel">
      <div class="ai-boundary-icon"><ShieldCheck :size="20" /></div>
      <div><strong>Pi Agent 研究权限边界</strong><p>Pi Agent 只读取调用方提供的冻结快照，输出可复核的解释、筛选条件、策略草案和诊断。它没有文件、命令、交易或通知工具，不能修改确定性决策、自动推送资格、模拟盘或真实订单。</p></div>
      <div class="ai-boundary-meta"><span>执行器 {{ statusValue('executor', 'pi_agent_worker') }}</span><span>决策影响 {{ statusValue('decision_effect', 'none') }}</span><span>Worker {{ workerState?.ready ? 'Pi Agent 已就绪' : workerState?.status || 'Pi Agent 未就绪' }}</span></div>
    </section>

    <div class="ai-workbench-grid">
      <aside class="panel ai-session-panel">
        <div class="panel-head">
          <div><h2>会话</h2><p>{{ sessions.length }} 个研究对话</p></div>
          <button class="icon-button" type="button" title="新建会话" aria-label="新建会话" @click="newSession"><Plus :size="17" /></button>
        </div>
        <div class="panel-body ai-session-body">
          <button class="button primary ai-new-session" type="button" @click="newSession"><Plus :size="15" />新建对话</button>
          <div v-if="!sessions.length" class="empty ai-session-empty"><MessageSquare :size="20" /><strong>还没有会话</strong><span>新建对话后，技能偏好和消息会持久化在当前工作区。</span></div>
          <div v-else class="ai-session-list">
            <div v-for="session in sessions" :key="session.id" class="ai-session-row" :class="{ active: session.id === activeSessionId }">
              <button type="button" class="ai-session-select" @click="loadSession(session.id)"><span class="ai-session-title">{{ shortText(session.title, '新对话') }}</span><span class="ai-session-meta">{{ session.message_count || 0 }} 条消息 · {{ formatTime(session.updated_at) }}</span></button>
              <button class="icon-button compact-icon" type="button" title="删除会话" aria-label="删除会话" :disabled="sessionDeleting" @click="deleteActiveSession(session)"><Trash2 :size="14" /></button>
            </div>
          </div>
        </div>
      </aside>

      <main class="ai-main-column">
        <div class="workspace-tabs ai-tabs" role="tablist" aria-label="AI 工作台视图">
          <button type="button" :class="{ active: activeTab === 'chat' }" :aria-selected="activeTab === 'chat'" @click="activeTab = 'chat'"><MessageSquare :size="15" />对话</button>
          <button type="button" :class="{ active: activeTab === 'research' }" :aria-selected="activeTab === 'research'" @click="activeTab = 'research'"><Sparkles :size="15" />研究技能</button>
          <button type="button" :class="{ active: activeTab === 'tasks' }" :aria-selected="activeTab === 'tasks'" @click="activeTab = 'tasks'"><Clock3 :size="15" />任务 <span v-if="tasks.length" class="ai-tab-count">{{ tasks.length }}</span></button>
          <button type="button" :class="{ active: activeTab === 'reports' }" :aria-selected="activeTab === 'reports'" @click="activeTab = 'reports'"><FileSearch :size="15" />报告 <span v-if="reports.length" class="ai-tab-count">{{ reports.length }}</span></button>
          <button type="button" :class="{ active: activeTab === 'settings' }" :aria-selected="activeTab === 'settings'" @click="activeTab = 'settings'"><Settings2 :size="15" />配置</button>
        </div>

        <section v-if="activeTab === 'chat'" class="ai-chat-layout">
          <section class="panel ai-chat-panel">
            <div class="panel-head">
              <div><h2>{{ shortText(activeSession?.title, '新对话') }}</h2><p>{{ activeSession ? '消息、技能选择和会话标题会保存在当前工作区。' : '选择或新建一个会话开始研究。' }}</p></div>
              <span v-if="activeSession" class="tag">{{ activeSession.id.slice(0, 8) }}</span>
            </div>
            <div class="panel-body ai-chat-body">
              <div class="ai-skill-picker">
                <div class="ai-section-label"><span>当前技能</span><small>可多选，改变会保存到会话</small></div>
                <div class="ai-skill-chips">
                  <button v-for="skill in availableSkills" :key="skill.id" type="button" class="ai-skill-chip" :class="{ selected: selectedSkillIds.includes(skill.id) }" :aria-pressed="selectedSkillIds.includes(skill.id)" @click="toggleSkill(skill.id)"><Sparkles :size="13" />{{ skill.name || skill.id }}</button>
                </div>
              </div>
              <div v-if="sessionLoading" class="empty ai-loading"><RefreshCw :size="18" class="spin" />加载会话…</div>
              <div v-else-if="!messageList.length" class="empty ai-chat-empty"><Bot :size="28" /><strong>从冻结输入开始</strong><span>可以问一个研究问题，也可以先在右侧加载单股研究快照。</span></div>
              <div v-else class="ai-message-list" aria-live="polite">
                <article v-for="message in messageList" :key="message.id || `${message.created_at}-${message.content}`" class="ai-message" :class="message.role === 'user' ? 'user' : 'assistant'">
                  <div class="ai-message-avatar"><UserRound v-if="message.role === 'user'" :size="15" /><Bot v-else :size="15" /></div>
                  <div class="ai-message-content"><div class="ai-message-meta"><strong>{{ message.role === 'user' ? '你' : 'AI 研究助手' }}</strong><span>{{ formatTime(message.created_at) }}</span></div><p>{{ message.content }}</p></div>
                </article>
              </div>
              <div v-if="chatSending" class="ai-stream-status"><RefreshCw :size="14" class="spin" />{{ chatProgress || '生成中…' }}<button class="button ghost" type="button" @click="stopChat"><Pause :size="14" />停止</button></div>
              <div v-if="chatError" class="error-box ai-inline-error"><CircleAlert :size="16" />{{ chatError }}</div>
              <div class="ai-composer">
                <textarea v-model="composer" :disabled="chatSending" aria-label="输入研究问题" placeholder="输入研究问题，例如：解释这份快照中技术和风险证据的冲突…" @keydown.enter.exact.prevent="sendChat" />
                <div class="ai-composer-footer"><span>{{ selectedSkillNames.length ? selectedSkillNames.join('、') : '通用研究' }} · {{ snapshot.instrument || '未选择标的' }}</span><button class="button primary" type="button" :disabled="chatSending || !composer.trim()" @click="sendChat"><Send :size="15" />发送</button></div>
              </div>
            </div>
          </section>
        </section>

        <section v-else-if="activeTab === 'research'" class="ai-research-view">
          <section class="panel">
            <div class="panel-head"><div><h2>研究技能</h2><p>快捷入口使用当前冻结快照；生产环境推荐提交到独立 Worker。</p></div><span class="tag">{{ snapshot.market || store.market }} / {{ snapshot.instrument || '未选择' }}</span></div>
            <div class="panel-body">
              <div class="ai-skill-grid">
                <button v-for="skill in quickSkills" :key="skill.id" type="button" class="ai-skill-card" :disabled="taskSubmitting" @click="setQuickTask(skill)"><span class="ai-skill-card-icon"><component :is="skill.icon" :size="18" /></span><span><strong>{{ skill.name }}</strong><small>{{ skill.description }}</small></span><ChevronRight :size="16" /></button>
              </div>
              <div class="ai-skill-runner">
                <div class="ai-section-label"><span>提交技能任务</span><small>请求 JSON 可补充已有回测、预测或研报文本</small></div>
                <div class="field-grid">
                  <div class="field"><label for="ai-task-kind">任务类型</label><select id="ai-task-kind" v-model="taskKind"><option value="analysis">多角色研究</option><option value="research">深度研究</option><option value="screening">自然语言选股</option><option value="interpretation">预测与因子解读</option><option value="strategy">策略草案</option><option value="diagnosis">回测诊断</option><option value="report_analysis">研报解读</option></select></div>
                  <div class="field"><label for="ai-task-profile">报告 profile</label><select id="ai-task-profile" v-model="taskProfile"><option value="quick">quick</option><option value="standard">standard</option><option value="research">research</option><option value="explain">explain</option></select></div>
                </div>
                <div class="field ai-task-question"><label for="ai-task-question">研究问题</label><textarea id="ai-task-question" v-model="taskQuestion" placeholder="描述要研究的条件、策略或报告内容" /></div>
                <div class="field"><label for="ai-task-request">补充请求 JSON</label><textarea id="ai-task-request" v-model="taskRequestText" class="code-input" spellcheck="false" /></div>
                <div v-if="taskMessage" class="ai-task-message" role="status"><CheckCircle2 :size="15" />{{ taskMessage }}</div>
                <div class="form-actions"><button class="button primary" type="button" :disabled="taskSubmitting" @click="submitTask(false)"><Play :size="15" />提交 Worker 任务</button><button class="button" type="button" :disabled="taskSubmitting" @click="submitTask(true)"><Gauge :size="15" />本地立即运行</button></div>
              </div>
            </div>
          </section>
        </section>

        <section v-else-if="activeTab === 'tasks'" class="ai-task-view">
          <div class="section-grid two">
            <section class="panel"><div class="panel-head"><div><h2>任务队列</h2><p>任务由独立 Pi Agent Worker 获取 lease 后执行。</p></div><button class="icon-button" type="button" title="刷新任务" aria-label="刷新任务" @click="loadTasks"><RefreshCw :size="16" /></button></div><div class="panel-body ai-task-list"><div v-if="!tasks.length" class="empty">暂无任务。先从研究技能提交一个任务。</div><button v-for="task in tasks" :key="task.id" type="button" class="ai-task-row" :class="{ active: task.id === activeTaskId }" @click="selectTask(task)"><span class="ai-task-row-main"><strong>{{ task.kind || 'analysis' }} · {{ task.profile || 'standard' }}</strong><small>{{ task.id.slice(0, 12) }} · {{ formatTime(task.created_at) }}</small></span><span class="tag" :class="taskStatusClass(task.status)">{{ taskStatusLabel(task.status) }}</span></button></div></section>
            <section class="panel"><div class="panel-head"><div><h2>任务详情</h2><p>{{ activeTask ? activeTask.id : '请选择任务' }}</p></div><div class="head-actions"><button v-if="activeTask && ['queued', 'failed', 'degraded'].includes(String(activeTask.status))" class="icon-button" type="button" title="运行任务" aria-label="运行任务" @click="runActiveTask"><Play :size="15" /></button><button v-if="activeTask && ['queued', 'running', 'cancel_requested'].includes(String(activeTask.status))" class="icon-button" type="button" title="取消任务" aria-label="取消任务" @click="cancelActiveTask"><Pause :size="15" /></button></div></div><div class="panel-body"><div v-if="!activeTask" class="empty">任务状态、运行拓扑和报告会显示在这里。</div><template v-else><div class="ai-task-summary"><span class="tag" :class="taskStatusClass(activeTask.status)">{{ taskStatusLabel(activeTask.status) }}</span><span>输入 hash {{ shortText(activeTask.context_hash, '尚未生成').slice(0, 16) }}</span><span>创建 {{ formatTime(activeTask.created_at) }}</span><span v-if="activeFlow">耗时 {{ formatDuration(activeFlow.summary.elapsed_ms) }}</span></div><section class="ai-flow-inspector" aria-label="AI 运行拓扑"><div class="ai-flow-head"><div><strong>运行拓扑</strong><small>入口 → 冻结 Context → provider/Agent → 报告 → 安全隔离</small></div><span v-if="flowLoading" class="flow-loading"><RefreshCw :size="13" class="spin" />刷新中</span><span v-else class="tag" :class="flowStatusClass(activeFlow?.status)">{{ flowStatusLabel(activeFlow?.status) }}</span></div><div v-if="!activeFlow" class="empty ai-flow-empty">当前任务还没有可展示的运行拓扑。</div><template v-else><div class="ai-flow-summary"><span><strong>{{ activeFlow.summary.data_source_count }}</strong> 数据节点</span><span><strong>{{ activeFlow.summary.failed_attempts }}</strong> 次失败</span><span><strong>{{ activeFlow.summary.retry_count }}</strong> 次重试</span><span><strong>{{ activeFlow.summary.fallback_count }}</strong> 次降级</span><span><strong>{{ activeFlow.summary.event_count }}</strong> 个事件</span></div><div class="ai-flow-board"><div v-for="lane in flowLanes" :key="lane.id" class="ai-flow-lane"><div class="ai-flow-lane-label"><span>{{ lane.label }}</span><small>{{ flowNodesForLane(lane.id).length }}</small></div><div class="ai-flow-lane-nodes"><button v-for="node in flowNodesForLane(lane.id)" :key="node.id" type="button" class="ai-flow-node" :class="[{ selected: node.id === selectedFlowNodeId }, flowStatusClass(node.status)]" @click="selectedFlowNodeId = node.id"><span class="ai-flow-node-top"><Layers3 :size="13" /><span class="tag" :class="flowStatusClass(node.status)">{{ flowStatusLabel(node.status) }}</span></span><strong>{{ node.label }}</strong><small>{{ node.provider || node.kind }}<span v-if="node.duration_ms != null"> · {{ formatDuration(node.duration_ms) }}</span></small></button><span v-if="!flowNodesForLane(lane.id).length" class="ai-flow-empty-lane">暂无节点</span></div></div></div><div v-if="selectedFlowNode" class="ai-flow-node-detail"><div><strong>{{ selectedFlowNode.label }}</strong><span class="tag" :class="flowStatusClass(selectedFlowNode.status)">{{ flowStatusLabel(selectedFlowNode.status) }}</span></div><p>{{ selectedFlowNode.message || '该节点没有附加说明。' }}</p><small v-if="selectedFlowNode.metadata">{{ prettyJson(selectedFlowNode.metadata) }}</small></div><div class="ai-flow-edges"><span v-for="edge in activeFlow.edges" :key="edge.id" class="ai-flow-edge" :class="flowStatusClass(edge.status)">{{ flowNodeLabel(edge.from) }} <ChevronRight :size="12" /> {{ flowNodeLabel(edge.to) }} <em>{{ edge.label || edge.kind }}</em></span></div><div class="ai-flow-events"><div class="ai-flow-event-tools"><strong>运行事件</strong><select v-model="flowEventFilter" aria-label="事件严重性筛选"><option value="all">全部事件</option><option value="info">信息</option><option value="success">成功</option><option value="warning">警告</option><option value="danger">错误</option></select><input v-model="flowEventSearch" aria-label="搜索运行事件" placeholder="搜索事件" /></div><div v-if="!filteredFlowEvents.length" class="empty ai-flow-empty">没有匹配的事件。</div><div v-else class="ai-flow-event-list"><div v-for="event in filteredFlowEvents" :key="event.id" class="ai-flow-event"><span class="ai-event-marker" :class="flowStatusClass(event.severity)"><CheckCircle2 v-if="event.severity === 'success'" :size="13" /><CircleAlert v-else-if="event.severity === 'danger'" :size="13" /><Clock3 v-else :size="13" /></span><div><strong>{{ event.title }}</strong><small>{{ event.message || event.type }} · {{ formatTime(event.timestamp) }}<span v-if="event.node_id"> · {{ flowNodeLabel(event.node_id) }}</span></small></div></div></div></div></template></section><div class="ai-event-list ai-raw-event-list"><div v-for="event in taskEvents" :key="String(event.id || `${event.event_type}-${event.created_at}`)" class="ai-event-row"><span class="ai-event-marker" :class="event.event_type === 'error' ? 'bad' : event.event_type === 'done' ? 'good' : ''"><CheckCircle2 v-if="event.event_type === 'done'" :size="13" /><CircleAlert v-else-if="event.event_type === 'error'" :size="13" /><Clock3 v-else :size="13" /></span><span><strong>{{ eventLabel(event) }}</strong><small>{{ eventDetail(event) }} · {{ formatTime(event.created_at) }}</small></span></div></div><div v-if="activeTask.report_id" class="form-actions"><button class="button primary" type="button" @click="activeTab = 'reports'; loadReport(String(activeTask?.report_id))"><FileSearch :size="15" />打开结构化报告</button></div><div v-if="taskLoading" class="ai-loading-line"><RefreshCw :size="14" class="spin" />正在刷新任务</div></template></div></section>
          </div>
        </section>

        <section v-else-if="activeTab === 'reports'" class="ai-report-view">
          <div class="section-grid two">
            <section class="panel"><div class="panel-head"><div><h2>结构化报告</h2><p>报告是非权威研究 artifact，带有输入 hash 和 provider provenance。</p></div><button class="icon-button" type="button" title="刷新报告" aria-label="刷新报告" @click="loadReports"><RefreshCw :size="16" /></button></div><div class="panel-body ai-report-list"><div v-if="reportLoading" class="empty"><RefreshCw :size="18" class="spin" />加载报告…</div><div v-else-if="!reports.length" class="empty">暂无 AI 报告。</div><button v-for="report in reports" :key="report.id" type="button" class="ai-report-row" :class="{ active: report.id === selectedReport?.id }" @click="chooseReport(report)"><span><strong>{{ report.body?.instrument || '未命名标的' }} · {{ report.body?.profile || 'research' }}</strong><small>{{ report.body?.market || '—' }} · {{ formatTime(report.created_at) }}</small></span><span class="tag" :class="report.body?.status === 'complete' ? 'good' : report.body?.status === 'unavailable' ? 'bad' : 'warn'">{{ report.body?.status || report.status || '—' }}</span></button></div></section>
            <section class="panel"><div class="panel-head"><div><h2>{{ reportBody.instrument || '报告详情' }}</h2><p>{{ reportBody.market || '—' }} · {{ reportBody.profile || '—' }} · 输入 {{ shortText(selectedReport?.context_hash, '—').slice(0, 16) }}</p></div><span class="tag" :class="reportBody.status === 'complete' ? 'good' : reportBody.status === 'unavailable' ? 'bad' : 'warn'">{{ reportBody.status || '—' }}</span></div><div class="panel-body ai-report-detail"><div v-if="!selectedReport" class="empty">选择一份报告查看综合结论和角色观点。</div><template v-else><div class="ai-report-callout"><ShieldCheck :size="17" /><span>非权威研究输出：{{ reportBody.decision_effect || 'none' }} · 不改变确定性决策或自动推送资格。</span></div><section v-if="reportSynthesis" class="ai-report-section"><h3>综合结论</h3><p class="ai-report-summary">{{ reportSynthesis.summary }}</p><div class="ai-report-columns"><div><strong>共同证据</strong><ul><li v-for="item in stringList(reportSynthesis.common_evidence)" :key="`common-${item}`">{{ item }}</li></ul></div><div><strong>分歧与风险</strong><ul><li v-for="item in [...stringList(reportSynthesis.disagreements), ...stringList(reportSynthesis.risks)]" :key="`risk-${item}`">{{ item }}</li></ul></div></div></section><section class="ai-report-section"><h3>角色观点</h3><div class="ai-opinion-list"><article v-for="opinion in reportOpinions" :key="opinion.role" class="ai-opinion-row"><div class="ai-opinion-head"><strong>{{ opinion.role }}</strong><span v-if="opinion.confidence != null" class="tag">置信 {{ Math.round(Number(opinion.confidence) * 100) }}%</span></div><p>{{ opinion.conclusion }}</p><small>证据 {{ stringList(opinion.evidence).join('；') || '—' }}</small></article><div v-if="!reportOpinions.length" class="empty">该报告没有成功生成角色观点。</div></div></section><section v-if="reportDsaBlocks.length" class="ai-report-section ai-dsa-section"><div class="ai-dsa-head"><div><h3>DSA 结构化复核</h3><p>按参考项目的 dashboard 区块展示；所有数值位、阶段动作和仓位建议仅供人工复核。</p></div><span class="tag warn">human review only</span></div><div class="ai-dsa-grid"><article v-for="block in reportDsaBlocks" :key="block.key" class="ai-dsa-block"><div class="ai-dsa-block-head"><strong>{{ block.title }}</strong><span>复核信息</span></div><template v-if="block.key === 'core_conclusion'"><p class="ai-dsa-lead">{{ dsaText(block.value.one_sentence) }}</p><div class="ai-dsa-facts"><span>信号 {{ dsaText(block.value.signal_type, '未说明') }}</span><span>时效 {{ dsaText(block.value.time_sensitivity, '未说明') }}</span></div><div v-if="block.value.position_advice" class="ai-dsa-note">无持仓：{{ dsaText(dsaValue(block.value, 'position_advice').no_position) }}<br />有持仓：{{ dsaText(dsaValue(block.value, 'position_advice').has_position) }}</div></template><template v-else-if="block.key === 'data_perspective'"><div class="ai-dsa-kv"><span>趋势</span><strong>{{ dsaText(dsaValue(block.value, 'trend_status').ma_alignment) }}</strong><span>趋势分数</span><strong>{{ dsaText(dsaValue(block.value, 'trend_status').trend_score) }}</strong><span>当前价</span><strong>{{ dsaText(dsaValue(block.value, 'price_position').current_price) }}</strong><span>支撑 / 阻力</span><strong>{{ dsaText(dsaValue(block.value, 'price_position').support_level) }} / {{ dsaText(dsaValue(block.value, 'price_position').resistance_level) }}</strong><span>量能</span><strong>{{ dsaText(dsaValue(block.value, 'volume_analysis').volume_status) }}</strong><span>筹码</span><strong>{{ dsaText(dsaValue(block.value, 'chip_structure').chip_health) }}</strong></div></template><template v-else-if="block.key === 'intelligence'"><p>{{ dsaText(block.value.latest_news) }}</p><div class="ai-dsa-list-pair"><div><strong>积极催化</strong><ul><li v-for="item in dsaList(block.value.positive_catalysts)" :key="`positive-${item}`">{{ item }}</li></ul></div><div><strong>风险提示</strong><ul><li v-for="item in dsaList(block.value.risk_alerts)" :key="`alert-${item}`">{{ item }}</li></ul></div></div><small>情绪 {{ dsaText(block.value.sentiment_summary) }} · 盈利展望 {{ dsaText(block.value.earnings_outlook) }}</small></template><template v-else-if="block.key === 'battle_plan'"><div class="ai-dsa-kv"><span>理想买入点</span><strong>{{ dsaText(dsaValue(block.value, 'sniper_points').ideal_buy) }}</strong><span>次优买入点</span><strong>{{ dsaText(dsaValue(block.value, 'sniper_points').secondary_buy) }}</strong><span>止损位</span><strong>{{ dsaText(dsaValue(block.value, 'sniper_points').stop_loss) }}</strong><span>目标位</span><strong>{{ dsaText(dsaValue(block.value, 'sniper_points').take_profit) }}</strong><span>仓位策略</span><strong>{{ dsaText(dsaValue(block.value, 'position_strategy').suggested_position) }}</strong></div><ul class="ai-limitation-list"><li v-for="item in dsaList(block.value.action_checklist)" :key="`check-${item}`">{{ item }}</li></ul></template><template v-else-if="block.key === 'phase_decision'"><div class="ai-dsa-facts"><span>窗口 {{ dsaText(block.value.action_window, '未说明') }}</span><span>下一检查 {{ dsaText(block.value.next_check_time, '未说明') }}</span></div><p>{{ dsaText(block.value.immediate_action) }}</p><ul class="ai-limitation-list"><li v-for="item in dsaList(block.value.watch_conditions)" :key="`watch-${item}`">{{ item }}</li></ul><small>置信理由：{{ dsaText(block.value.confidence_reason) }}</small></template><template v-else-if="block.key === 'signal_attribution'"><div class="ai-attribution-list"><div v-for="item in [['technical_indicators', '技术指标'], ['news_sentiment', '新闻情绪'], ['fundamentals', '基本面'], ['market_conditions', '市场环境']]" :key="item[0]" class="ai-attribution-row"><span>{{ item[1] }}</span><div><i :style="{ width: `${Math.min(100, Math.max(0, Number(block.value[item[0]]) || 0))}%` }" /></div><strong>{{ dsaPercent(block.value[item[0]]) }}</strong></div></div><p>最强看多：{{ dsaText(block.value.strongest_bullish_signal) }}<br />最强看空：{{ dsaText(block.value.strongest_bearish_signal) }}</p></template><template v-else><div class="ai-dsa-list-pair"><div><strong>角色分歧</strong><ul><li v-for="opinion in (Array.isArray(block.value.base_opinions) ? block.value.base_opinions : [])" :key="String(opinion.agent)">{{ opinion.agent }} · {{ opinion.stance }}<span v-if="opinion.confidence != null"> · {{ dsaPercent(Number(opinion.confidence) * 100) }}</span></li></ul></div><div><strong>数据退化事件</strong><ul><li v-for="item in dsaList(block.value.degraded_events)" :key="`degraded-${item}`">{{ item }}</li></ul></div></div><p>{{ dsaText(block.value.risk_control_summary) }}</p><small>数据质量：{{ dsaText(block.value.data_quality) }} · {{ dsaText(block.value.decision_path) }}</small></template></article></div></section><section v-if="reportLimitations.length" class="ai-report-section"><h3>限制与诊断</h3><ul class="ai-limitation-list"><li v-for="item in reportLimitations" :key="item">{{ item }}</li></ul></section><details class="ai-provenance"><summary><Code2 :size="14" />查看 provenance 与原始诊断</summary><pre>{{ prettyJson({ provenance: reportBody.provenance, diagnostics: reportBody.diagnostics }) }}</pre></details></template></div></section>
          </div>
        </section>

        <section v-else class="ai-settings-view">
          <div class="section-grid two">
            <section class="panel"><div class="panel-head"><div><h2>Provider 与模型</h2><p>只填写环境变量引用，例如 env://OPENAI_API_KEY。</p></div><button class="button" type="button" @click="resetProviderForm"><Plus :size="15" />新 provider</button></div><div class="panel-body"><div v-if="!channels.length" class="empty">当前没有可用 provider。未配置时 AI 会降级为可见的 unavailable 报告。</div><div v-else class="ai-provider-list"><div v-for="channel in channels" :key="channel.id" class="ai-provider-row"><div><strong>{{ channel.name }}</strong><small>{{ channel.protocol || 'openai_compatible' }} · {{ channel.model || '未指定模型' }} · {{ channel.secret_available ? '凭证已配置' : '凭证未配置' }}</small><small class="ai-provider-capability-line">{{ readinessLabel(channel.readiness?.overall) }} · JSON {{ capabilityState(channel.capabilities?.structured_json) }} · Stream {{ capabilityState(channel.capabilities?.stream) }}</small></div><div class="head-actions"><span class="tag" :class="channel.enabled === false ? 'bad' : readinessClass(channel.readiness?.overall)">{{ channel.enabled === false ? '停用' : readinessLabel(channel.readiness?.overall) }}</span><button class="icon-button compact-icon" type="button" title="编辑 provider" aria-label="编辑 provider" @click="editProvider(channel)"><Settings2 :size="14" /></button></div></div></div><div v-if="capabilityRows.length" class="ai-capability-matrix"><div class="ai-section-label"><span>能力矩阵</span><small>能力声明与 readiness 分开显示</small></div><div v-for="provider in capabilityRows" :key="provider.id" class="ai-capability-row"><strong>{{ provider.provider || provider.id }}</strong><span>{{ readinessLabel(record(provider.readiness).overall) }}</span><span>结构化 {{ capabilityState(record(provider.capabilities).structured_json) }}</span><span>报告 {{ capabilityState(record(provider.capabilities).structured_report) }}</span><span>追踪 {{ capabilityState(record(provider.capabilities).provider_trace) }}</span></div></div><div class="ai-provider-form"><div class="field-grid"><div class="field"><label for="ai-provider-id">ID</label><input id="ai-provider-id" v-model="providerForm.id" :disabled="Boolean(providerEditingId)" placeholder="openai-main" /></div><div class="field"><label for="ai-provider-name">名称</label><input id="ai-provider-name" v-model="providerForm.name" placeholder="OpenAI 主通道" /></div><div class="field"><label for="ai-provider-protocol">协议</label><select id="ai-provider-protocol" v-model="providerForm.protocol"><option value="openai_compatible">OpenAI-compatible</option><option value="litellm">LiteLLM</option><option value="local_cli">本地 CLI</option><option value="pi_agent">Pi Agent（隔离无工具）</option></select></div><div class="field"><label for="ai-provider-model">模型</label><input id="ai-provider-model" v-model="providerForm.model" placeholder="gpt-4o-mini" /></div><div class="field"><label for="ai-provider-base-url">Base URL</label><input id="ai-provider-base-url" v-model="providerForm.base_url" placeholder="https://api.openai.com/v1" /></div><div class="field"><label for="ai-provider-secret">secret_ref</label><input id="ai-provider-secret" v-model="providerForm.secret_ref" placeholder="env://OPENAI_API_KEY" autocomplete="off" /></div></div><label class="check-control"><input v-model="providerForm.enabled" type="checkbox" />启用这个通道</label><div class="form-actions"><button class="button primary" type="button" :disabled="providerSaving" @click="saveProvider"><Save :size="15" />{{ providerEditingId ? '保存修改' : '保存 provider' }}</button><button v-if="providerEditingId" class="button" type="button" @click="resetProviderForm">取消编辑</button></div></div></div></section>
            <section class="panel"><div class="panel-head"><div><h2>运行状态</h2><p>Worker 和 provider 状态只用于可见性，不代表交易能力。</p></div><Bot :size="19" class="faint" /></div><div class="panel-body"><div class="metric-grid"><div class="metric-cell"><span>运行时</span><strong>{{ statusValue('runtime', '—') }}</strong></div><div class="metric-cell"><span>Worker</span><strong>{{ workerState?.ready ? '进程已就绪' : workerState?.status || '未就绪' }}</strong></div><div class="metric-cell"><span>已验证 provider</span><strong>{{ channels.filter((channel) => channel.readiness?.ready === true).length }}</strong></div></div><div class="ai-status-list"><div><span>Lease</span><strong>{{ workerState?.lease_name || 'ai-worker' }}</strong></div><div><span>Provider 影响</span><strong>{{ statusValue('decision_effect', 'none') }}</strong></div><div><span>降级规则</span><strong>{{ statusValue('degradation_policy', '失败可见，不取得推送资格') }}</strong></div></div><div class="ai-model-list"><div class="ai-section-label"><span>模型目录</span><small>{{ models.length ? '来自已配置通道；可用表示已真实验证' : '未发现模型' }}</small></div><div v-for="model in models" :key="String(model.id || model.model)" class="ai-model-row"><span>{{ model.model || model.id }}</span><span class="tag" :class="model.available ? 'good' : 'warn'">{{ model.available ? '已验证' : '未验证' }}</span></div></div><div class="ai-attempt-history"><div class="ai-section-label"><span>最近尝试</span><small>仅保留 provider、模型和状态</small></div><div v-if="!providerAttempts.length" class="empty ai-attempt-empty">尚无 retry/fallback 记录。</div><div v-else class="ai-attempt-list"><div v-for="attempt in providerAttempts" :key="`${attempt.provider}-${attempt.attempt}-${attempt.recorded_at}`" class="ai-attempt-row"><span class="tag" :class="attempt.status === 'success' ? 'good' : attempt.relation === 'fallback' ? 'warn' : 'bad'">{{ attempt.relation === 'fallback' ? '降级' : attempt.relation === 'retry' ? '重试' : '首次' }}</span><span><strong>{{ attempt.provider || 'provider' }}</strong><small>{{ attempt.model || '未指定模型' }} · {{ attempt.status || '—' }} · {{ formatDuration(attempt.duration_ms) }}</small></span><span>{{ shortText(attempt.error_code, '—') }}</span></div></div></div></div></section>
          </div>
        </section>

        <section class="panel ai-compat-panel">
          <div class="panel-head"><div><h2>兼容审计</h2><p>保留原有 Agent registry、研究任务和操作审计，作为 AI 工作台之外的历史能力视图。</p></div><span class="tag">Agentic API</span></div>
          <div class="panel-body ai-compat-grid"><div><strong>Agent registry</strong><span>{{ legacyAgents.length }} 个</span></div><div><strong>研究任务</strong><span>{{ legacyResearch.length }} 条</span></div><div><strong>操作审计</strong><span>{{ legacyOperations.length }} 条</span></div><div><strong>订单权限</strong><span class="good">不提供</span></div></div>
        </section>
      </main>

      <aside class="panel ai-context-panel">
        <div class="panel-head"><div><h2>冻结研究上下文</h2><p>所有 AI 请求都携带这份输入。</p></div><Database :size="18" class="faint" /></div>
        <div class="panel-body">
          <div class="ai-context-state"><span class="tag" :class="snapshot.authoritative === false ? 'warn' : snapshot.quality_status === 'available' ? 'good' : 'warn'">{{ snapshot.authoritative === false ? '仅人工研究' : snapshot.quality_status || 'unknown' }}</span><span>{{ snapshot.market || store.market }} / {{ snapshot.instrument || '未选择标的' }}</span></div>
          <div class="field ai-snapshot-loader"><label for="ai-snapshot-symbol">从单股研究加载</label><div class="ai-inline-form"><input id="ai-snapshot-symbol" v-model="snapshotSymbol" placeholder="600519" @keydown.enter.prevent="loadResearchSnapshot" /><button class="icon-button" type="button" title="加载研究快照" aria-label="加载研究快照" :disabled="snapshotLoading" @click="loadResearchSnapshot"><RefreshCw :size="15" :class="{ spin: snapshotLoading }" /></button></div></div>
          <div v-if="snapshotError" class="error-box ai-inline-error"><CircleAlert :size="15" />{{ snapshotError }}</div>
          <div class="ai-snapshot-meta"><span>来源 {{ shortText(snapshot.source) }}</span><span>冻结时间 {{ formatTime(snapshot.as_of) }}</span><span>证据 {{ snapshot.evidence?.length || 0 }} 条</span></div>
          <div v-if="snapshot.authoritative === false" class="ai-context-warning"><CircleAlert :size="15" /><span>当前冻结输入含外部回退行情，仅用于人工研究；不会成为确定性决策、风险判断或自动推送的权威输入。{{ snapshot.fallback_reason ? `原因：${snapshot.fallback_reason}` : '' }}</span></div>
          <div class="field"><label for="ai-snapshot-json">快照 JSON</label><textarea id="ai-snapshot-json" v-model="snapshotText" class="code-input ai-snapshot-editor" spellcheck="false" @input="snapshotDirty = true" /></div>
          <div class="form-actions"><button class="button" type="button" :disabled="!snapshotDirty" @click="applySnapshotText"><Save :size="15" />应用并冻结</button><button class="button ghost" type="button" @click="snapshotText = prettyJson(snapshot); snapshotDirty = false"><RotateCcw :size="15" />还原</button></div>
          <div class="ai-context-warning"><ShieldCheck :size="15" /><span>快照改变后会产生新的 context hash。AI 不能读取快照之外的实时事实，也不能把报告变成决策动作。</span></div>
        </div>
      </aside>
    </div>
  </section>
</template>
