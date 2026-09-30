<script setup lang="ts">
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { OrderItemRecord } from '../../types/results'

const props = defineProps<{ item: OrderItemRecord }>()
const quantity = computed(() => finitePositiveInteger(props.item.quantity))
const total = computed(() => {
  const explicit = finiteAmount(props.item.totalPrice)
  if (explicit != null) return explicit
  const unitPrice = finiteAmount(props.item.unitPrice)
  return unitPrice != null && quantity.value != null ? unitPrice * quantity.value : null
})
</script>

<template>
  <div class="order-item-row">
    <div>
      <strong>{{ customerCopy(item.productName || '商品名称待确认') }}</strong>
      <span>数量 × {{ quantity ?? '—' }}</span>
    </div>
    <span>{{ formatCurrency(total, '金额待确认') }}</span>
  </div>
</template>

<style scoped>
.order-item-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding-block: var(--space-2); border-bottom: 1px solid var(--color-line); }.order-item-row:last-child { border-bottom: 0; }.order-item-row div { display: grid; gap: var(--space-1); }.order-item-row strong { color: var(--color-ink); }.order-item-row div span { color: var(--color-muted); font-size: var(--text-sm); }.order-item-row > span { color: var(--color-navy); font-weight: 800; }
</style>
