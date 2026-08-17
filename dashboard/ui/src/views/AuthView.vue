<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, Eye, EyeOff, KeyRound, LockKeyhole, UserRound } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api } from '../api/client'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const router = useRouter()
const route = useRoute()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const inviteCode = ref('')
const displayName = ref('')
const email = ref('')
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')

const title = computed(() => mode.value === 'login' ? '回到你的研究工作区' : '创建研究工作区')
const submitLabel = computed(() => busy.value ? '处理中…' : mode.value === 'login' ? '登录工作区' : '创建并登录')

function validate() {
  const cleanUsername = username.value.trim()
  if (!/^[A-Za-z0-9_.-]{3,32}$/.test(cleanUsername)) return '用户名需为 3-32 位字母、数字、下划线、点或横线'
  if (password.value.length < 8) return '密码至少需要 8 位'
  if (mode.value === 'register' && inviteCode.value.trim().length !== 6) return '邀请码必须是 6 位'
  if (mode.value === 'register' && email.value.trim() && !/^\S+@\S+\.\S+$/.test(email.value.trim())) return '邮箱格式不正确'
  return ''
}

async function submit() {
  error.value = validate()
  if (error.value || busy.value) return
  busy.value = true
  try {
    const result = mode.value === 'login'
      ? await api.login(username.value.trim(), password.value)
      : await api.register({ username: username.value.trim(), password: password.value, invite_code: inviteCode.value.trim().toUpperCase(), display_name: displayName.value.trim() || undefined, email: email.value.trim() || undefined })
    store.setAccount(result)
    await store.loadWorkspace()
    const destination = typeof route.query.next === 'string' && route.query.next.startsWith('/app/') ? route.query.next : '/app/decision'
    await router.replace(destination)
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '认证失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

function switchMode(next: 'login' | 'register') {
  mode.value = next
  error.value = ''
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-intro">
      <div class="auth-brand"><span class="brand-mark">AQ</span><span><strong>AI Quant</strong><small>决策工作台</small></span></div>
      <div class="auth-intro-copy"><span class="eyebrow">可复现的量化研究闭环</span><h1>让每个结论都能回到它的证据。</h1><p>从行情、单股研究到验证和结构化报告，在同一个工作区里保留输入、版本、风险状态与 AI 解释。</p><div class="auth-trust"><span><LockKeyhole :size="16" />AI 只做解释</span><span><KeyRound :size="16" />凭证只保留引用</span></div></div>
    </section>
    <section class="auth-card panel" aria-labelledby="auth-title">
      <div class="auth-card-head"><span class="auth-kicker">工作区访问</span><h2 id="auth-title">{{ title }}</h2><p>{{ mode === 'login' ? '登录后继续查看自选池、决策和报告。' : '使用邀请码加入一个隔离的个人研究工作区。' }}</p></div>
      <div class="auth-tabs" role="tablist" aria-label="认证方式"><button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button><button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button></div>
      <form class="auth-form" @submit.prevent="submit">
        <div class="field"><label for="auth-username">用户名</label><div class="input-with-icon"><UserRound :size="17" /><input id="auth-username" v-model="username" autocomplete="username" required placeholder="例如 quant_user" /></div></div>
        <div class="field"><label for="auth-password">密码</label><div class="input-with-icon"><LockKeyhole :size="17" /><input id="auth-password" v-model="password" :type="showPassword ? 'text' : 'password'" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" required placeholder="至少 8 位" /><button class="input-action" type="button" :title="showPassword ? '隐藏密码' : '显示密码'" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="17" /><Eye v-else :size="17" /></button></div></div>
        <template v-if="mode === 'register'"><div class="field"><label for="auth-invite">邀请码</label><div class="input-with-icon"><KeyRound :size="17" /><input id="auth-invite" v-model="inviteCode" autocomplete="one-time-code" maxlength="6" required placeholder="6 位邀请码" /></div></div><div class="field-grid"><div class="field"><label for="auth-display-name">显示名称 <span class="muted">可选</span></label><input id="auth-display-name" v-model="displayName" autocomplete="name" maxlength="60" placeholder="研究者" /></div><div class="field"><label for="auth-email">邮箱 <span class="muted">可选</span></label><input id="auth-email" v-model="email" autocomplete="email" maxlength="120" placeholder="name@example.com" /></div></div></template>
        <div v-if="error" class="error-box" role="alert">{{ error }}</div>
        <button class="button primary auth-submit" type="submit" :disabled="busy"><span>{{ submitLabel }}</span><ArrowRight :size="17" /></button>
      </form>
      <p class="auth-footnote">研究状态、报告与操作记录按 workspace 隔离；登录不会授予真实下单权限。</p>
    </section>
  </main>
</template>
