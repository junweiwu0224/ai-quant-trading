<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, LockKeyhole, RefreshCw, ShieldOff } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import BrokerDisableGuard from '../components/guards/BrokerDisableGuard.vue'

// LIVE TRADING DISABLED
// This view is read-only and shows mock/sanitized data only

const config = ref<Record<string, any> | null>(null)
const types = ref<Array<Record<string, any>>>([])
const gatewayInfo = ref<Record<string, any> | null>(null)
const loading = ref(false)
const message = ref('')

async function load() {
  loading.value = true
  message.value = ''
  try {
    const [configResponse, typesResponse, gatewayResponse] = await Promise.all([api.brokerConfig(), api.brokerTypeCatalog(), api.brokerGatewayInfo()])
    config.value = configResponse
    types.value = Array.isArray(typesResponse) ? typesResponse : []
    gatewayInfo.value = gatewayResponse
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Broker 状态加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <BrokerDisableGuard />

  <section>
    <div class="page-head"><div><RouterLink to="/app/settings" class="muted small"><ArrowLeft :size="14" />系统设置</RouterLink><h1>Broker 与实盘设置</h1><p>只展示经过脱敏的账户配置和网关能力。当前阶段禁止真实下单、撤单和凭证变更，页面没有绕过安全边界的按钮。</p></div><button class="button" type="button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button></div>
    <div v-if="message" class="error-box" role="alert">{{ message }}</div>
    <section class="panel"><div class="panel-head"><div><h2>当前配置</h2><p>API 应已屏蔽 auth_code；页面再次以只读方式展示。</p></div><LockKeyhole :size="18" class="good" /></div><div class="panel-body"><div v-if="!config" class="empty">暂无 Broker 配置。</div><div v-else class="check-list"><div v-for="(value, key) in config" :key="String(key)" class="check-row"><span>{{ key }}</span><span class="tag">{{ typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—') }}</span></div></div></div></section>
    <div class="section-grid two" style="margin-top:18px"><section class="panel"><div class="panel-head"><div><h2>网关类型</h2><p>显示已声明能力，不代表本机已连接。</p></div><ShieldOff :size="18" class="faint" /></div><div class="panel-body"><div v-if="!types.length" class="empty">暂无网关类型。</div><div v-else class="check-list"><div v-for="(item, index) in types" :key="String(item.value || index)" class="check-row"><div class="check-copy"><strong>{{ item.label || item.value }}</strong><span>{{ item.description || item.status || '—' }}</span></div><span class="tag warn">仅声明</span></div></div></div></section><section class="panel"><div class="panel-head"><div><h2>安全状态</h2><p>实盘能力保持显式禁用，使用旧入口也不能跳过本阶段约束。</p></div></div><div class="panel-body"><div class="error-box">真实券商联调需要单独确认凭证、网络、账户和下单影响范围。当前 Vue 页面不保存或发送任何交易凭证。</div><div v-if="gatewayInfo" class="data-source" style="margin-top:14px"><span>网关描述已读取</span><span>{{ Object.keys(gatewayInfo).length }} 个顶层字段</span></div></div></section></div>
  </section>
</template>
