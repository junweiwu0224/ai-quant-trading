<script setup lang="ts">
import { Check, CircleAlert, X } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../../api/client'

const props = defineProps<{
  orders: Record<string, any>[]
  canOperate: boolean
  saving: boolean
}>()

const emit = defineEmits<{ refresh: []; 'update:saving': [v: boolean] }>()

const orderForm = ref({ code: '', direction: 'buy', order_type: 'market', price: null as number | null, volume: 100, strategy_name: 'manual', signal_reason: '人工确认的模拟盘订单' })
const pendingCancel = ref<string | null>(null)
const actionFeedback = ref('')
const actionError = ref('')

function requireOperable() {
  if (props.canOperate) return true
  actionError.value = '当前 paper 运行状态不可确认，已禁用此操作。'
  return false
}

async function submitOrder() {
  if (!requireOperable()) return
  if (!orderForm.value.code.trim() || orderForm.value.volume < 100 || orderForm.value.volume % 100 !== 0 || (orderForm.value.order_type !== 'market' && !(Number(orderForm.value.price) > 0))) {
    actionError.value = '请检查：股票代码非空、数量 ≥100 且为 100 的整数倍、限价单需指定价格。'
    return
  }
  emit('update:saving', true)
  actionFeedback.value = ''; actionError.value = ''
  try {
    await api.createPaperOrder({
      code: orderForm.value.code.trim(),
      direction: orderForm.value.direction,
      order_type: orderForm.value.order_type,
      price: orderForm.value.order_type === 'limit' ? orderForm.value.price : undefined,
      volume: orderForm.value.volume,
      strategy_name: orderForm.value.strategy_name,
      signal_reason: orderForm.value.signal_reason,
    })
    actionFeedback.value = '订单已提交；请等待 worker/撮合状态确认'
    orderForm.value.code = ''
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '下单失败' }
  finally { emit('update:saving', false) }
}

async function cancelOrder(order: Record<string, any>) {
  const orderId = order.id || order.order_id
  if (!orderId || !requireOperable()) return
  pendingCancel.value = orderId
  actionFeedback.value = ''; actionError.value = ''
  try {
    await api.cancelPaperOrder(orderId)
    actionFeedback.value = '撤单已提交；等待确认'
    emit('refresh')
  } catch (e: any) { actionError.value = e?.data?.detail || e?.message || '撤单失败' }
  finally { pendingCancel.value = null }
}
</script>

<template>
  <div class="section-grid two">
    <section class="panel">
      <div class="panel-head">
        <div><h2>提交新订单</h2><p>只创建 paper 动作；提交后等待 worker/撮合状态，不代表已成交。</p></div>
      </div>
      <form class="form-grid" @submit.prevent="submitOrder">
        <label>股票代码<input v-model="orderForm.code" placeholder="000001" required /></label>
        <label>方向<div class="button-row"><button type="button" :class="['button', orderForm.direction === 'buy' ? 'primary' : 'ghost']" @click="orderForm.direction = 'buy'">买入</button><button type="button" :class="['button', orderForm.direction === 'sell' ? 'danger' : 'ghost']" @click="orderForm.direction = 'sell'">卖出</button></div></label>
        <label>类型<div class="select-wrap"><select v-model="orderForm.order_type"><option value="market">市价</option><option value="limit">限价</option></select></div></label>
        <label v-if="orderForm.order_type === 'limit'">价格<input v-model.number="orderForm.price" type="number" step="0.01" min="0" /></label>
        <label>数量<input v-model.number="orderForm.volume" type="number" min="100" step="100" /></label>
        <label>策略名<input v-model="orderForm.strategy_name" placeholder="manual" /></label>
        <label>信号原因<input v-model="orderForm.signal_reason" /></label>
        <div class="button-row"><button class="button primary" type="submit" :disabled="saving || !canOperate"><Check :size="15" />提交订单</button></div>
      </form>
      <div v-if="actionError" class="error-box" role="alert"><CircleAlert :size="16" />{{ actionError }}</div>
      <div v-if="actionFeedback" class="info-box" role="status" aria-live="polite"><Check :size="16" />{{ actionFeedback }}</div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <div><h2>挂单与成交</h2><p>pending/部分成交/已取消 只代表当前状态；已取消订单不影响持仓。</p></div>
        <span class="tag">{{ orders.length }} 个订单</span>
      </div>
      <div v-if="!orders.length" class="empty">暂无订单记录</div>
      <div v-else class="table-wrap">
        <table class="table" aria-label="paper 订单">
          <thead><tr><th>代码</th><th>方向</th><th>类型</th><th>价格</th><th>数量</th><th>状态</th><th>时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id || order.order_id">
              <td>{{ order.code || order.instrument || '—' }}</td>
              <td><span :class="order.direction === 'buy' ? 'good' : 'bad'">{{ order.direction === 'buy' ? '买入' : '卖出' }}</span></td>
              <td>{{ order.order_type || order.type || '—' }}</td>
              <td>{{ order.price ?? '市价' }}</td>
              <td>{{ order.volume ?? order.quantity ?? '—' }}</td>
              <td><span class="tag">{{ order.status || '—' }}</span></td>
              <td>{{ order.created_at || '—' }}</td>
              <td><button v-if="['pending','open'].includes(order.status)" class="button ghost small" type="button" :disabled="pendingCancel === (order.id || order.order_id)" @click="cancelOrder(order)"><X :size="14" />{{ pendingCancel === (order.id || order.order_id) ? '撤单中' : '撤单' }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
