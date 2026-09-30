<script setup lang="ts">
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { CartRecord } from '../../types/results'

const props = defineProps<{ item: CartRecord }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const quantity = computed(() => finitePositiveInteger(props.item.quantity))
const price = computed(() => finiteAmount(props.item.price))
const subtotal = computed(() =>
  quantity.value != null && price.value != null ? quantity.value * price.value : null,
)
const productName = computed(() => props.item.productName?.trim() || '该商品')
</script>

<template>
  <article class="cart-card">
    <div class="main">
      <span>购物车商品</span>
      <h4>{{ customerCopy(item.productName || '商品名称待确认') }}</h4>
      <p>{{ formatCurrency(item.price) }} / 件</p>
    </div>
    <dl class="metrics">
      <div><dt>数量</dt><dd>{{ quantity ?? '—' }}</dd></div>
      <div><dt>小计</dt><dd>{{ formatCurrency(subtotal, '金额待确认') }}</dd></div>
    </dl>
    <footer>
      <button
        type="button"
        :disabled="item.productId == null"
        @click="emit('prompt', { prompt: `查看「${productName}」的商品详情`, label: '查看商品详情', authRequired: false })"
      >
        商品详情
      </button>
      <button
        type="button"
        :disabled="item.cartId == null || quantity == null"
        @click="emit('prompt', { prompt: `将购物车中「${productName}」的数量改为 ${(quantity ?? 0) + 1} 件`, label: '修改个人购物车', authRequired: true })"
      >
        调整数量
      </button>
      <button
        class="danger"
        type="button"
        :disabled="item.cartId == null"
        @click="emit('prompt', { prompt: `从购物车移除「${productName}」`, label: '移出个人购物车商品', authRequired: true })"
      >
        移出购物车
      </button>
    </footer>
  </article>
</template>

<style scoped>
.cart-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-4); padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
.main { display: grid; gap: var(--space-1); }.main > span, .main p { color: var(--color-muted); font-size: var(--text-sm); }.main h4 { color: var(--color-navy); font-size: var(--text-lg); }
.metrics { display: grid; grid-template-columns: repeat(2, minmax(6rem, 1fr)); gap: var(--space-2); margin: 0; }.metrics div { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-surface-subtle); border-radius: var(--radius-md); }.metrics dt { color: var(--color-muted); font-size: var(--text-xs); }.metrics dd { margin: 0; color: var(--color-navy); font-weight: 800; }
footer { display: flex; grid-column: 1 / -1; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-2); }button { min-height: var(--control-height-md); padding-inline: var(--space-3); color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); font-weight: 700; }.danger { color: var(--color-danger); border-color: var(--color-danger); }button:disabled { opacity: 0.5; }
@media (max-width: 680px) { .cart-card { grid-template-columns: minmax(0, 1fr); }.metrics, footer { grid-column: 1; }.metrics { grid-template-columns: 1fr 1fr; }footer { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }footer button { white-space: nowrap; }footer .danger { grid-column: 1 / -1; } }
</style>
