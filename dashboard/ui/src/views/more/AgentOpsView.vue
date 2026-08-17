<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import BaseCard from '../../components/base/BaseCard.vue'
import BaseButton from '../../components/base/BaseButton.vue'
import BaseTag from '../../components/base/BaseTag.vue'
import { Bot, RefreshCw, Play, Square, RotateCw, AlertCircle } from 'lucide-vue-next'
import { getAgentStatus, getAgentTasks, getAgentLogs } from '../../api/agent'
import type { AgentStatus, AgentTask, AgentLog } from '../../api/agent'

const title = 'Agent 运维监控'
const description = 'AI Agent 监控、任务管理与运维工具'

// State
const loading = ref(false)
const error = ref<string | null>(null)
const agentStatus = ref<AgentStatus | null>(null)
const tasks = ref<AgentTask[]>([])
const logs = ref<AgentLog[]>([])

// Filter state
const taskFilter = ref<string>('all')
const logFilter = ref<string>('all')

// Computed
const filteredTasks = computed(() => {
  if (taskFilter.value === 'all') {
    return tasks.value
  }
  return tasks.value.filter(t => t.status === taskFilter.value)
})

const filteredLogs = computed(() => {
  if (logFilter.value === 'all') {
    return logs.value
  }
  return logs.value.filter(l => l.level === logFilter.value)
})

// Methods
async function loadData() {
  loading.value = true
  error.value = null

  try {
    const [statusData, tasksData, logsData] = await Promise.all([
      getAgentStatus(),
      getAgentTasks(20),
      getAgentLogs(50)
    ])

    agentStatus.value = statusData
    tasks.value = tasksData
    logs.value = logsData
  } catch (err) {
    console.error('Failed to load agent data:', err)
    error.value = '加载Agent数据失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function getTaskStatusVariant(status: string): 'success' | 'warning' | 'info' | 'danger' {
  const variantMap: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    running: 'info',
    queued: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return variantMap[status] || 'default' as any
}

function getTaskStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    running: '运行中',
    queued: '排队中',
    completed: '已完成',
    failed: '失败'
  }
  return labelMap[status] || status
}

function getPriorityVariant(priority: string): 'danger' | 'warning' | 'default' {
  const variantMap: Record<string, 'danger' | 'warning' | 'default'> = {
    high: 'danger',
    normal: 'warning',
    low: 'default'
  }
  return variantMap[priority] || 'default'
}

function getPriorityLabel(priority: string): string {
  const labelMap: Record<string, string> = {
    high: '高',
    normal: '中',
    low: '低'
  }
  return labelMap[priority] || priority
}

function getLogLevelVariant(level: string): 'info' | 'warning' | 'danger' | 'default' {
  const variantMap: Record<string, 'info' | 'warning' | 'danger' | 'default'> = {
    info: 'info',
    warning: 'warning',
    error: 'danger',
    debug: 'default'
  }
  return variantMap[level] || 'default'
}

function getLogLevelLabel(level: string): string {
  const labelMap: Record<string, string> = {
    info: 'INFO',
    warning: 'WARN',
    error: 'ERROR',
    debug: 'DEBUG'
  }
  return labelMap[level] || level.toUpperCase()
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}分钟`
  } else {
    return `${Math.floor(seconds / 3600)}小时`
  }
}

function formatNumber(num: number): string {
  return num.toLocaleString('zh-CN')
}

function formatPercent(num: number): string {
  return num.toFixed(1) + '%'
}

function handleAgentControl(action: string) {
  alert(`Agent控制功能开发中\n\n操作: ${action}\n\n提示：将支持启动、停止、重启等Agent控制操作`)
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="page-container">
    <div class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <div class="head-actions">
        <BaseButton
          variant="ghost"
          size="sm"
          :loading="loading"
          @click="loadData"
        >
          <RefreshCw :size="16" />
          刷新
        </BaseButton>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <!-- Loading State -->
    <div v-if="loading && !agentStatus" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Main Content -->
    <div v-else-if="agentStatus" class="content-grid">
      <!-- Agent Status Dashboard -->
      <BaseCard padding="lg" class="dashboard-card">
        <h2 class="section-title">Agent状态概览</h2>
        <div class="dashboard-grid">
          <div class="dashboard-item">
            <div class="dashboard-icon agents">
              <Bot :size="24" />
            </div>
            <div class="dashboard-content">
              <div class="dashboard-label">总Agent数</div>
              <div class="dashboard-value">{{ agentStatus.total_agents }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-icon active">
              <Play :size="24" />
            </div>
            <div class="dashboard-content">
              <div class="dashboard-label">运行中</div>
              <div class="dashboard-value success">{{ agentStatus.active_agents }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-icon idle">
              <Square :size="24" />
            </div>
            <div class="dashboard-content">
              <div class="dashboard-label">空闲</div>
              <div class="dashboard-value">{{ agentStatus.idle_agents }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-icon error">
              <AlertCircle :size="24" />
            </div>
            <div class="dashboard-content">
              <div class="dashboard-label">异常</div>
              <div class="dashboard-value danger">{{ agentStatus.error_agents }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-content">
              <div class="dashboard-label">运行任务</div>
              <div class="dashboard-value">{{ agentStatus.tasks_running }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-content">
              <div class="dashboard-label">排队任务</div>
              <div class="dashboard-value">{{ agentStatus.tasks_queued }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-content">
              <div class="dashboard-label">今日完成</div>
              <div class="dashboard-value">{{ agentStatus.tasks_completed_today }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-content">
              <div class="dashboard-label">成功率</div>
              <div class="dashboard-value success">{{ formatPercent(agentStatus.success_rate) }}</div>
            </div>
          </div>

          <div class="dashboard-item">
            <div class="dashboard-content">
              <div class="dashboard-label">平均耗时</div>
              <div class="dashboard-value">{{ formatDuration(agentStatus.avg_task_duration) }}</div>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Task Queue Table -->
      <BaseCard padding="lg" class="tasks-card">
        <div class="section-header">
          <h2 class="section-title">任务队列</h2>
          <div class="filter-tabs">
            <button
              class="filter-tab"
              :class="{ active: taskFilter === 'all' }"
              @click="taskFilter = 'all'"
            >
              全部
            </button>
            <button
              class="filter-tab"
              :class="{ active: taskFilter === 'running' }"
              @click="taskFilter = 'running'"
            >
              运行中
            </button>
            <button
              class="filter-tab"
              :class="{ active: taskFilter === 'queued' }"
              @click="taskFilter = 'queued'"
            >
              排队中
            </button>
            <button
              class="filter-tab"
              :class="{ active: taskFilter === 'completed' }"
              @click="taskFilter = 'completed'"
            >
              已完成
            </button>
            <button
              class="filter-tab"
              :class="{ active: taskFilter === 'failed' }"
              @click="taskFilter = 'failed'"
            >
              失败
            </button>
          </div>
        </div>

        <div v-if="filteredTasks.length === 0" class="empty-state">
          暂无任务
        </div>
        <div v-else class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>任务ID</th>
                <th>Agent</th>
                <th>任务类型</th>
                <th>描述</th>
                <th>优先级</th>
                <th>状态</th>
                <th>开始时间</th>
                <th class="align-right">进度/耗时</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in filteredTasks" :key="task.id">
                <td class="code">{{ task.id }}</td>
                <td>{{ task.agent_name }}</td>
                <td class="task-type">{{ task.task_type }}</td>
                <td class="task-description">{{ task.description }}</td>
                <td>
                  <BaseTag :variant="getPriorityVariant(task.priority)" size="sm">
                    {{ getPriorityLabel(task.priority) }}
                  </BaseTag>
                </td>
                <td>
                  <BaseTag :variant="getTaskStatusVariant(task.status)" size="sm">
                    {{ getTaskStatusLabel(task.status) }}
                  </BaseTag>
                </td>
                <td class="timestamp">
                  {{ task.start_time ? formatDateTime(task.start_time) : '-' }}
                </td>
                <td class="align-right">
                  <span v-if="task.status === 'running' && task.progress">
                    {{ task.progress }}%
                  </span>
                  <span v-else-if="task.duration">
                    {{ formatDuration(task.duration) }}
                  </span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </BaseCard>

      <!-- Log Viewer -->
      <BaseCard padding="lg" class="logs-card">
        <div class="section-header">
          <h2 class="section-title">执行日志</h2>
          <div class="filter-tabs">
            <button
              class="filter-tab"
              :class="{ active: logFilter === 'all' }"
              @click="logFilter = 'all'"
            >
              全部
            </button>
            <button
              class="filter-tab"
              :class="{ active: logFilter === 'error' }"
              @click="logFilter = 'error'"
            >
              错误
            </button>
            <button
              class="filter-tab"
              :class="{ active: logFilter === 'warning' }"
              @click="logFilter = 'warning'"
            >
              警告
            </button>
            <button
              class="filter-tab"
              :class="{ active: logFilter === 'info' }"
              @click="logFilter = 'info'"
            >
              信息
            </button>
          </div>
        </div>

        <div class="log-viewer">
          <div
            v-for="log in filteredLogs"
            :key="log.id"
            class="log-entry"
            :class="`log-${log.level}`"
          >
            <span class="log-timestamp">{{ formatDateTime(log.timestamp) }}</span>
            <BaseTag :variant="getLogLevelVariant(log.level)" size="sm" class="log-level">
              {{ getLogLevelLabel(log.level) }}
            </BaseTag>
            <span class="log-agent">{{ log.agent_name }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </BaseCard>

      <!-- Agent Control Panel -->
      <BaseCard padding="lg" class="control-card">
        <h2 class="section-title">Agent控制面板</h2>
        <p class="section-hint">集中管理所有Agent的启动、停止和重启操作</p>

        <div class="control-actions">
          <BaseButton
            variant="primary"
            size="md"
            :disabled="true"
            @click="handleAgentControl('start')"
          >
            <Play :size="16" />
            启动（功能开发中）
          </BaseButton>
          <BaseButton
            variant="danger"
            size="md"
            :disabled="true"
            @click="handleAgentControl('stop')"
          >
            <Square :size="16" />
            停止（功能开发中）
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="md"
            :disabled="true"
            @click="handleAgentControl('restart')"
          >
            <RotateCw :size="16" />
            重启（功能开发中）
          </BaseButton>
        </div>
      </BaseCard>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      暂无数据
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: var(--spacing-xl);
  max-width: 1600px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
}

.page-head h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin-bottom: var(--spacing-xs);
}

.page-head p {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
  margin: 0;
}

.head-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.error-banner {
  padding: var(--spacing-md) var(--spacing-lg);
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
  border-left: 3px solid var(--color-danger);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-lg);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-3xl);
  color: var(--color-ink-soft);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-line);
  border-top-color: var(--color-accent);
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
  margin-bottom: var(--spacing-md);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.content-grid {
  display: grid;
  gap: var(--spacing-lg);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0;
}

.section-hint {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
  margin: var(--spacing-sm) 0 var(--spacing-lg) 0;
}

.filter-tabs {
  display: flex;
  gap: var(--spacing-xs);
}

.filter-tab {
  padding: var(--spacing-xs) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}

.filter-tab:hover {
  background-color: var(--color-surface-muted);
  border-color: var(--color-ink-faint);
}

.filter-tab.active {
  background-color: var(--color-accent);
  color: var(--color-surface);
  border-color: var(--color-accent);
}

/* Dashboard */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-lg);
}

.dashboard-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: var(--color-surface-muted);
  border-radius: var(--radius-md);
}

.dashboard-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.dashboard-icon.agents {
  background-color: var(--color-info-bg);
  color: var(--color-info);
}

.dashboard-icon.active {
  background-color: var(--color-success-bg);
  color: var(--color-success);
}

.dashboard-icon.idle {
  background-color: var(--color-surface-strong);
  color: var(--color-ink-soft);
}

.dashboard-icon.error {
  background-color: var(--color-danger-bg);
  color: var(--color-danger);
}

.dashboard-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  flex: 1;
}

.dashboard-label {
  font-size: var(--font-size-sm);
  color: var(--color-ink-soft);
}

.dashboard-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.dashboard-value.success {
  color: var(--color-success);
}

.dashboard-value.danger {
  color: var(--color-danger);
}

/* Tables */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.data-table th {
  text-align: left;
  padding: var(--spacing-sm) var(--spacing-md);
  background-color: var(--color-surface-muted);
  color: var(--color-ink-soft);
  font-weight: var(--font-weight-medium);
  border-bottom: 1px solid var(--color-line);
  white-space: nowrap;
}

.data-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-line);
  color: var(--color-ink);
}

.data-table tbody tr:hover {
  background-color: var(--color-surface-muted);
}

.data-table .align-right {
  text-align: right;
}

.data-table .code {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
  color: var(--color-ink-soft);
}

.data-table .task-type {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
}

.data-table .task-description {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-table .timestamp {
  color: var(--color-ink-soft);
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

/* Log Viewer */
.log-viewer {
  max-height: 500px;
  overflow-y: auto;
  padding: var(--spacing-md);
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
}

.log-entry {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) 0;
  border-bottom: 1px solid var(--color-line);
}

.log-entry:last-child {
  border-bottom: none;
}

.log-timestamp {
  color: var(--color-ink-soft);
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.log-level {
  flex-shrink: 0;
}

.log-agent {
  color: var(--color-ink-soft);
  white-space: nowrap;
  font-size: var(--font-size-xs);
}

.log-message {
  color: var(--color-ink);
  flex: 1;
  word-break: break-word;
}

.log-entry.log-error .log-message {
  color: var(--color-danger);
}

.log-entry.log-warning .log-message {
  color: var(--color-warn);
}

/* Control Panel */
.control-actions {
  display: flex;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--color-ink-soft);
  font-size: var(--font-size-sm);
}

@media (max-width: 768px) {
  .page-container {
    padding: var(--spacing-lg);
  }

  .page-head {
    flex-direction: column;
    gap: var(--spacing-md);
  }

  .dashboard-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .filter-tabs {
    flex-wrap: wrap;
  }

  .table-container {
    font-size: var(--font-size-xs);
  }

  .control-actions {
    flex-direction: column;
  }

  .control-actions button {
    width: 100%;
  }
}
</style>
