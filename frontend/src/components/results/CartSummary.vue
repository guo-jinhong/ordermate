<script setup lang="ts">
import { computed } from 'vue'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { CartRecord } from '../../types/results'

const props = defineProps<{ items: CartRecord[] }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const summary = computed(() => {
  const quantities = props.items.map((item) => finitePositiveInteger(item.quantity))
  const subtotals = props.items.map((item, index) => {
    const price = finiteAmount(item.price)
    const quantity = quantities[index]
    return price != null && quantity != null ? price * quantity : null
  })
  return {
    itemCount: quantities.reduce<number>((total, value) => total + (value ?? 0), 0),
    completeQuantity: quantities.every((value) => value != null),
    completeTotal: subtotals.every((value) => value != null),
    hasKnownTotal: subtotals.some((value) => value != null),
    total: subtotals.reduce<number>((total, value) => total + (value ?? 0), 0),
  }
})
</script>

<template>
  <section class="cart-summary" aria-label="购物车汇总">
    <div>
      <span>
        {{ items.length }} 种商品 ·
        {{ summary.completeQuantity ? `共 ${summary.itemCount} 件` : '部分数量待确认' }}
      </span>
      <strong v-if="summary.hasKnownTotal">
        {{ summary.completeTotal ? '合计' : '已知金额' }} {{ formatCurrency(summary.total) }}
      </strong>
      <strong v-else>合计金额待确认</strong>
    </div>
    <button
      type="button"
      @click="emit('prompt', { prompt: '清空我的购物车', label: '清空个人购物车', authRequired: true })"
    >
      清空购物车
    </button>
  </section>
</template>

<style scoped>
.cart-summary { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-4); color: var(--color-on-dark); background: var(--color-navy-raised); border-radius: var(--radius-lg); }.cart-summary div { display: grid; gap: var(--space-1); }.cart-summary span { color: var(--color-on-dark-muted); font-size: var(--text-sm); }.cart-summary strong { font-size: var(--text-lg); }.cart-summary button { min-height: var(--control-height-md); padding-inline: var(--space-4); color: var(--color-danger-soft); background: transparent; border: 1px solid var(--color-danger); border-radius: var(--radius-md); font-weight: 700; }
@media (max-width: 680px) { .cart-summary { align-items: stretch; flex-direction: column; }.cart-summary button { width: 100%; } }
</style>
