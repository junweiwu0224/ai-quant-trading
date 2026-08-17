<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import BaseButton from '../base/BaseButton.vue'
import { WARNINGS } from '../../config/features'

const STORAGE_KEY = 'broker-disable-acknowledged'

const showWarning = ref(false)

onMounted(() => {
  const acknowledged = localStorage.getItem(STORAGE_KEY)
  if (!acknowledged) {
    showWarning.value = true
  }
})

const handleAcknowledge = () => {
  localStorage.setItem(STORAGE_KEY, 'true')
  showWarning.value = false
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showWarning" class="broker-disable-overlay">
      <div class="broker-disable-backdrop" @click="handleAcknowledge"></div>
      <div class="warning-card">
        <div class="warning-icon">
          <AlertTriangle :size="48" />
        </div>
        <h2>{{ WARNINGS.liveTradingDisabled }}</h2>
        <div class="warning-content">
          <p>{{ WARNINGS.platformPurpose }}</p>
          <p>{{ WARNINGS.simulationOnly }}</p>
        </div>
        <BaseButton @click="handleAcknowledge" size="lg">
          我已知晓
        </BaseButton>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.broker-disable-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg);
}

.broker-disable-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
}

.warning-card {
  position: relative;
  z-index: 1;
  background-color: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: var(--spacing-2xl);
  max-width: 500px;
  width: 100%;
  box-shadow: var(--shadow-lg);
  text-align: center;
  animation: slideIn var(--duration-normal) var(--ease-smooth);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.warning-icon {
  display: flex;
  justify-content: center;
  margin-bottom: var(--spacing-lg);
  color: var(--color-warn);
}

.warning-card h2 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-ink);
  margin: 0 0 var(--spacing-lg) 0;
}

.warning-content {
  margin-bottom: var(--spacing-xl);
  text-align: left;
}

.warning-content p {
  font-size: var(--font-size-base);
  color: var(--color-ink-soft);
  line-height: var(--line-height-relaxed);
  margin: 0 0 var(--spacing-md) 0;
}

.warning-content p:last-child {
  margin-bottom: 0;
}

@media (max-width: 640px) {
  .broker-disable-overlay {
    padding: var(--spacing-md);
  }

  .warning-card {
    padding: var(--spacing-xl);
  }

  .warning-card h2 {
    font-size: var(--font-size-xl);
  }
}
</style>
