<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CircleAlert, Database, LockKeyhole, LogOut, Save, ServerCog } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const router = useRouter()
const markets = ref<any[]>([])
const status = ref<any | null>(null)
const workspace = ref<any | null>(null)
const preferences = ref({ daily_research_enabled: true, screening_enabled: true })
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const loggingOut = ref(false)
const workerProcessReady = computed(() => Boolean(status.value?.worker_process_ready ?? status.value?.worker_readiness?.ready))
const workerAutomationEnabled = computed(() => Boolean(status.value?.worker_automation_enabled ?? status.value?.worker_enabled))

async function load() {
  loading.value = true
  try {
    const [marketResponse, statusResponse, workspaceResponse] = await Promise.all([
      api.get<{ items: any[] }>('/api/decisions/markets'),
      api.get('/api/decisions/status'),
      api.get<any>('/api/account/workspace'),
    ])
    markets.value = marketResponse.items || []
    status.value = statusResponse
    workspace.value = workspaceResponse.workspace || null
    const settings = workspace.value?.settings || {}
    preferences.value = {
      daily_research_enabled: settings.daily_research_enabled !== false,
      screening_enabled: settings.screening_enabled !== false,
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '设置数据加载失败'
  } finally {
    loading.value = false
  }
}

async function savePreferences() {
  saving.value = true
  try {
    const response = await api.put<any>('/api/account/workspace/settings', { settings: { ...preferences.value } })
    workspace.value = response.workspace || workspace.value
    message.value = '研究与界面设置已保存；自动推送开关仍需通过资格接口操作'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '设置保存失败'
  } finally {
    saving.value = false
  }
}

async function logout() {
  loggingOut.value = true
  try {
    await api.logout()
  } finally {
    store.clearAccount()
    loggingOut.value = false
    await router.replace('/auth')
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head"><div><h1>工作区设置</h1><p>市场开关只表达研究范围；自动推送能力由数据源、版本验证和渠道资格共同决定。</p></div><div class="head-actions"><button class="button" :disabled="loading" type="button" @click="load">刷新</button><button class="button danger" :disabled="loggingOut" type="button" @click="logout"><LogOut :size="15" />{{ loggingOut ? '退出中' : '退出登录' }}</button></div></div>
    <div v-if="message" class="error-box" role="status">{{ message }}</div>
    <div class="section-grid two">
      <section class="panel">
        <div class="panel-head"><div><h2>运行状态</h2><p>Dashboard 是控制面，独立 Worker 才拥有调度和投递权。</p></div><ServerCog :size="18" class="faint" /></div>
        <div class="panel-body"><div class="check-list"><div class="check-row"><div class="check-copy"><strong>决策 Worker 进程</strong><span>独立进程、lease 和 outbox consumer 的实时 readiness</span></div><span class="tag" :class="workerProcessReady ? 'good' : 'bad'">{{ workerProcessReady ? '进程已就绪' : '进程未就绪' }}</span></div><div class="check-row"><div class="check-copy"><strong>工作区自动任务</strong><span>是否允许当前 workspace 参与 Worker 调度；与进程是否存活分开</span></div><span class="tag" :class="workerAutomationEnabled ? 'good' : 'warn'">{{ workerAutomationEnabled ? '已启用' : '默认关闭' }}</span></div><div class="check-row"><div class="check-copy"><strong>自动推送</strong><span>只能由通过资格的组合申请启用</span></div><span class="tag" :class="status?.auto_push_enabled ? 'good' : 'warn'">{{ status?.auto_push_enabled ? '已启用' : '未启用' }}</span></div><div class="check-row"><div class="check-copy"><strong>数据存储</strong><span>输入快照与报告存放在独立 decisions.db</span></div><Database :size="18" class="good" /></div><div class="check-row"><div class="check-copy"><strong>凭证边界</strong><span>前端和报告只显示 secret_ref，不保存密钥正文</span></div><LockKeyhole :size="18" class="good" /></div></div></div>
      </section>
      <section class="panel">
        <div class="panel-head"><div><h2>研究与入口设置</h2><p>这些开关只影响研究体验和默认入口，不改变历史报告。</p></div><Save :size="18" class="faint" /></div>
        <div class="panel-body"><div class="check-list"><label class="check-row"><span class="check-copy"><strong>研究日报</strong><span>允许工作区生成研究日报任务</span></span><input v-model="preferences.daily_research_enabled" type="checkbox" /></label><label class="check-row"><span class="check-copy"><strong>选股研究</strong><span>允许使用筛选与选股工作台</span></span><input v-model="preferences.screening_enabled" type="checkbox" /></label><div class="check-row"><span class="check-copy"><strong>统一决策工作台</strong><span>所有登录后的业务入口都使用当前工作台；历史链接会自动落到对应流程。</span></span><span class="tag good">已启用</span></div></div><div class="form-actions"><button class="button primary" :disabled="saving" type="button" @click="savePreferences"><Save :size="15" />{{ saving ? '保存中' : '保存设置' }}</button></div></div>
      </section>
    </div>
    <section class="panel" style="margin-top:18px">
      <div class="panel-head"><div><h2>市场能力矩阵</h2><p>市场切换器与能力边界独立，未接入 provider 的市场不会生成自动信号。</p></div></div>
      <div class="panel-body"><div class="check-list"><div v-for="market in markets" :key="market.market" class="check-row"><div class="check-copy"><strong>{{ market.label }} <span class="tag">{{ market.market }}</span></strong><span>{{ market.source }} · {{ market.fallback_reason }}</span></div><span class="tag" :class="market.automatic_push ? 'good' : 'warn'">{{ market.automatic_push ? '可自动推送' : '仅研究' }}</span></div></div></div>
    </section>
    <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>安全边界</h2><p>当前阶段不连接券商、不调用真实 Webhook、不执行外部 LLM。</p></div><CircleAlert :size="18" class="faint" /></div><div class="panel-body"><div class="error-box">需要真实 provider、外部通知或 cloudflared 联调时，必须单独确认外部影响范围。关机或断网期间 Worker 会延迟，系统不会伪造“已发送”。</div></div></section>
  </section>
</template>
