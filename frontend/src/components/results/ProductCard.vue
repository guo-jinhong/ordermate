<script setup lang="ts">
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { finiteAmount, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { ProductRecord, ProductSearchContext } from '../../types/results'

const props = defineProps<{ product: ProductRecord; context: ProductSearchContext }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const stock = computed(() => {
  if (props.product.stock == null || props.product.stock === '') return null
  const value = Number(props.product.stock)
  return Number.isFinite(value) && value >= 0 ? value : null
})
const active = computed(
  () => props.product.status == null || props.product.status === '' || Number(props.product.status) === 1,
)
const availability = computed(() => {
  if (!active.value) return { label: '已下架', tone: 'inactive' }
  if (stock.value == null) return { label: '库存待确认', tone: 'unknown' }
  if (stock.value > 0) return { label: '有货', tone: 'available' }
  return { label: '暂时缺货', tone: 'sold-out' }
})
const purchasable = computed(() => active.value && stock.value != null && stock.value > 0)
const productName = computed(() => props.product.name?.trim() || '该商品')
const matchReasons = computed(() => {
  const reasons: string[] = []
  const price = finiteAmount(props.product.price)
  const maxPrice = finiteAmount(props.context.max_price)
  const minPrice = finiteAmount(props.context.min_price)
  if (typeof props.context.keyword === 'string' && props.context.keyword.trim()) {
    reasons.push(`匹配“${props.context.keyword.trim()}”`)
  }
  if (price != null && maxPrice != null && price <= maxPrice) {
    reasons.push(`符合 ${formatCurrency(maxPrice)} 预算`)
  }
  if (price != null && minPrice != null && price >= minPrice) {
    reasons.push(`满足 ${formatCurrency(minPrice)} 起的价格范围`)
  }
  if (stock.value != null && stock.value > 0 && (props.context.in_stock === true || reasons.length === 0)) {
    reasons.push('当前有货')
  }
  return reasons.slice(0, 3)
})

const request = (action: PromptAction): void => emit('prompt', action)
</script>

<template>
  <article class="product-card">
    <div class="topline">
      <span>商品信息</span>
      <span class="availability" :data-tone="availability.tone">{{ availability.label }}</span>
    </div>
    <h4>{{ customerCopy(product.name || '未命名商品') }}</h4>
    <strong class="price">{{ formatCurrency(product.price) }}</strong>
    <p v-if="product.description" class="description">{{ customerCopy(product.description) }}</p>
    <dl v-if="stock != null" class="facts">
      <div v-if="stock != null"><dt>库存</dt><dd>{{ stock }} 件</dd></div>
    </dl>
    <div v-if="matchReasons.length" class="match">
      <span>匹配依据</span>
      <ul><li v-for="reason in matchReasons" :key="reason">{{ reason }}</li></ul>
    </div>
    <footer>
      <button
        type="button"
        :disabled="product.id == null"
        @click="request({ prompt: `查看「${productName}」的商品详情`, label: '查看商品详情', authRequired: false })"
      >
        查看详情
      </button>
      <button
        class="primary"
        type="button"
        :disabled="product.id == null || !purchasable"
        @click="request({ prompt: `将「${productName}」加入购物车，数量 1 件`, label: '加入个人购物车', authRequired: true })"
      >
        {{ purchasable ? '加入购物车' : '暂不可购买' }}
      </button>
    </footer>
  </article>
</template>

<style scoped>
.product-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
.topline, footer, .facts, .facts div { display: flex; align-items: center; }.topline, footer { justify-content: space-between; gap: var(--space-3); }.topline > span:first-child { color: var(--color-muted); font-size: var(--text-sm); }
.availability { padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 800; }.availability[data-tone="available"] { color: var(--color-success); background: var(--color-success-soft); }.availability[data-tone="sold-out"], .availability[data-tone="inactive"] { color: var(--color-danger); background: var(--color-danger-soft); }.availability[data-tone="unknown"] { color: var(--color-warning); background: var(--color-warning-soft); }
h4 { color: var(--color-navy); font-size: var(--text-xl); }.price { color: var(--color-primary-ink); font-size: var(--text-xl); }.description { color: var(--color-muted); line-height: var(--leading-relaxed); }
.facts { gap: var(--space-5); margin: 0; }.facts div { gap: var(--space-2); }.facts dt { color: var(--color-muted); }.facts dd { margin: 0; font-weight: 700; }
.match { display: grid; gap: var(--space-2); }.match > span { color: var(--color-muted); font-size: var(--text-sm); }.match ul { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }.match li { padding: var(--space-1) var(--space-2); color: var(--color-primary-ink); background: var(--color-primary-soft); border-radius: var(--radius-pill); font-size: var(--text-xs); }
footer { justify-content: flex-end; }button { min-height: var(--control-height-md); padding-inline: var(--space-4); color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); font-weight: 700; }.primary { color: var(--color-on-primary); background: var(--color-primary); border-color: var(--color-primary); }button:disabled { opacity: 0.5; }
</style>
