<script setup lang="ts">
import { computed } from 'vue'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { CartRecord } from '../../types/results'

const props = withDefaults(defineProps<{ items: CartRecord[]; busy?: boolean; managing?: boolean }>(), { busy: false, managing: false })
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
    hasKnownTotal: props.items.length === 0 || subtotals.some((value) => value != null),
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
    <button v-if="managing"
      type="button"
      :disabled="busy"
      @click="emit('prompt', { prompt: '清空我的购物车', label: '清空个人购物车', authRequired: true, preserveScroll: true })"
    >
      清空购物车
    </button>
  </section>
</template>

<style scoped>
.cart-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 0 12px; }
.cart-summary div { display: flex; flex-direction: column-reverse; gap: 4px; }
.cart-summary span { color: var(--color-muted); font-size: 13px; }
.cart-summary strong { color: var(--color-navy); font-size: 21px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.cart-summary button { min-height: 44px; padding: 0 8px; color: var(--color-danger); background: transparent; border: 0; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
