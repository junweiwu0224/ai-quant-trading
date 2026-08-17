<script setup lang="ts">
import { ref, computed } from 'vue'
import BaseCard from '../base/BaseCard.vue'
import BaseInput from '../base/BaseInput.vue'
import BaseSelect from '../base/BaseSelect.vue'
import BaseButton from '../base/BaseButton.vue'
import type { SelectOption } from '../base/BaseSelect.vue'

export interface BacktestDraftProps {
  market: string
  symbol: string
}

const props = defineProps<BacktestDraftProps>()

// Form state
const strategyName = ref(`${props.symbol} 策略草案`)
const timePeriod = ref('最近一年')
const initialCapital = ref(100000)
const positionSizing = ref('fixed-ratio')
const stopLoss = ref(5)
const takeProfit = ref(10)

// Position sizing options
const positionOptions: SelectOption[] = [
  { label: '固定金额', value: 'fixed-amount' },
  { label: '固定比例', value: 'fixed-ratio' },
  { label: '动态调整', value: 'dynamic' }
]

// Format currency for display
const formattedCapital = computed(() => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(initialCapital.value)
})

// Handlers
const handleSaveDraft = () => {
  // Placeholder - functionality in development
  console.log('Save draft clicked')
}

const handleRunBacktest = () => {
  // Placeholder - functionality in development
  console.log('Run backtest clicked')
}
</script>

<template>
  <BaseCard padding="lg" bordered>
    <h2 class="draft-title">回测配置</h2>

    <form class="draft-form" @submit.prevent>
      <!-- Strategy Name -->
      <div class="form-group">
        <label class="form-label">策略名称</label>
        <BaseInput
          v-model="strategyName"
          type="text"
          placeholder="输入策略名称"
        />
      </div>

      <!-- Time Period -->
      <div class="form-group">
        <label class="form-label">时间区间</label>
        <BaseInput
          v-model="timePeriod"
          type="text"
          placeholder="选择时间区间"
          disabled
        />
        <p class="form-hint">日期选择器开发中</p>
      </div>

      <!-- Initial Capital -->
      <div class="form-group">
        <label class="form-label">初始资金</label>
        <BaseInput
          v-model="initialCapital"
          type="number"
          placeholder="输入初始资金"
        />
        <p class="form-hint">当前设置: {{ formattedCapital }}</p>
      </div>

      <!-- Position Sizing -->
      <div class="form-group">
        <label class="form-label">仓位管理</label>
        <BaseSelect
          v-model="positionSizing"
          :options="positionOptions"
          placeholder="选择仓位管理方式"
        />
      </div>

      <!-- Stop Loss & Take Profit -->
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">止损比例 (%)</label>
          <BaseInput
            v-model="stopLoss"
            type="number"
            placeholder="5"
          />
        </div>
        <div class="form-group">
          <label class="form-label">止盈比例 (%)</label>
          <BaseInput
            v-model="takeProfit"
            type="number"
            placeholder="10"
          />
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="form-actions">
        <BaseButton
          variant="secondary"
          :disabled="true"
          @click="handleSaveDraft"
        >
          保存草案
        </BaseButton>
        <BaseButton
          variant="primary"
          :disabled="true"
          @click="handleRunBacktest"
        >
          运行回测
        </BaseButton>
      </div>
    </form>
  </BaseCard>
</template>

<style scoped>
.draft-title {
  margin: 0 0 var(--spacing-xl) 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
}

.draft-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
}

.form-hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-ink-faint);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
}

.form-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-line);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column;
  }
}
</style>
