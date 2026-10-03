<script setup lang="ts">
import { ShoppingCart } from '@lucide/vue'
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { ProductRecord, ProductSearchContext } from '../../types/results'

const props = withDefaults(defineProps<{ product: ProductRecord; context: ProductSearchContext; busy?: boolean; compact?: boolean }>(), { busy: false, compact: false })
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const stock = computed(() => {
  if (props.product.stock == null || props.product.stock === '') return null
  const value = Number(props.product.stock)
  return Number.isSafeInteger(value) && value >= 0 ? value : null
})
const active = computed(
  () => props.product.status == null || props.product.status === '' || Number(props.product.status) === 1,
)
const availability = computed(() => {
  if (!active.value) return { label: '已下架', tone: 'inactive' }
  if (stock.value == null) return { label: '购买状态待确认', tone: 'unknown' }
  if (stock.value > 0) return { label: '有货', tone: 'available' }
  return { label: '暂时缺货', tone: 'sold-out' }
})
const purchasable = computed(() => active.value && stock.value != null && stock.value > 0)
// 卡片操作绑定业务主键，展示名称不参与编号解析。
const productId = computed(() => finitePositiveInteger(props.product.id))
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
  return reasons.slice(0, 3)
})

const request = (action: PromptAction): void => emit('prompt', action)
</script>

<template>
  <article class="product-card" :class="{ compact }">
    <div class="topline">
      <h4><button class="product-title" type="button" :disabled="busy || productId == null" @click="request({ prompt: `查看商品 ${productId} 的详情`, displayPrompt: `查看「${productName}」的商品详情`, label: '查看商品详情', authRequired: false })">{{ customerCopy(product.name || '商品名称暂未显示') }}</button></h4>
      <span class="availability" :data-tone="availability.tone">{{ availability.label }}</span>
    </div>
    <strong class="price">{{ formatCurrency(product.price) }}</strong>
    <p v-if="!compact && product.description" class="description">{{ customerCopy(product.description) }}</p>
    <!-- 可用商品总量不代表每次操作的购买上限，仅展示购买状态。 -->
    <dl v-if="purchasable" class="facts">
      <div><dt>购买提示</dt><dd>有货，可加入购物车</dd></div>
    </dl>
    <div v-if="!compact && matchReasons.length" class="match">
      <ul><li v-for="reason in matchReasons" :key="reason">{{ reason }}</li></ul>
    </div>
    <footer>
      <button
        v-if="!compact" type="button"
        :disabled="busy || productId == null"
        @click="request({ prompt: `查看商品 ${productId} 的详情`, displayPrompt: `查看「${productName}」的商品详情`, label: '查看商品详情', authRequired: false })"
      >
        查看详情
      </button>
      <button
        class="primary"
        type="button"
        :disabled="busy || productId == null || !purchasable"
        @click="request({ prompt: `将商品 ${productId} 加入购物车，数量 1 件`, displayPrompt: `将「${productName}」加入购物车，数量 1 件`, label: '加入个人购物车', authRequired: true })"
      >
        <ShoppingCart :size="16" aria-hidden="true" />
        {{ purchasable ? '加入购物车' : '暂不可购买' }}
      </button>
    </footer>
  </article>
</template>

<style scoped>
.product-card { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard); }
.topline, footer, .facts, .facts div { display: flex; align-items: center; }.topline, footer { justify-content: space-between; gap: var(--space-3); }.topline > span:first-child { color: var(--color-muted); font-size: var(--text-sm); }
.availability { padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 800; }.availability[data-tone="available"] { color: var(--color-success); background: var(--color-success-soft); }.availability[data-tone="sold-out"], .availability[data-tone="inactive"] { color: var(--color-danger); background: var(--color-danger-soft); }.availability[data-tone="unknown"] { color: var(--color-warning); background: var(--color-warning-soft); }
h4 { color: var(--color-navy); font-size: var(--text-lg); }.price { color: var(--color-primary-ink); font-size: 1.5rem; letter-spacing: -0.03em; }.description { color: var(--color-muted); line-height: var(--leading-relaxed); }
.facts { gap: var(--space-5); margin: 0; }.facts div { gap: var(--space-2); }.facts dt { color: var(--color-muted); }.facts dd { margin: 0; font-weight: 700; }
.match { display: grid; gap: var(--space-2); }.match > span { color: var(--color-muted); font-size: var(--text-sm); }.match ul { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }.match li { padding: var(--space-1) var(--space-2); color: var(--color-primary-ink); background: var(--color-primary-soft); border-radius: var(--radius-pill); font-size: var(--text-xs); }
footer { margin-top: auto; padding-top: var(--space-3); border-top: 1px solid var(--color-line); justify-content: space-between; }footer button { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); min-height: var(--control-height-md); padding-inline: var(--space-4); color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); font-weight: 700; }.primary { color: var(--color-on-primary); background: var(--color-primary); border-color: var(--color-primary); }button:disabled { opacity: 0.5; }
.product-card:hover { border-color: var(--color-primary); box-shadow: var(--shadow-md); }
.topline { align-items: flex-start; }.availability { flex: 0 0 auto; white-space: nowrap; }
.product-title { padding: 0; min-height: 0; color: var(--color-ink); text-align: left; font-size: var(--text-lg); font-weight: 650; line-height: 1.45; overflow-wrap: anywhere; background: transparent; border: 0; }.product-title:hover:not(:disabled) { color: var(--color-primary-ink); text-decoration: underline; }
.description { font-size: var(--text-sm); overflow-wrap: anywhere; }
button:disabled { cursor: not-allowed; }
.compact { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; padding: 12px; border-radius: 12px; box-shadow: none; }
.compact .topline { grid-column: 1 / -1; }
.compact .price { grid-column: 1; font-size: 18px; overflow-wrap: anywhere; }
.compact .facts { color: var(--color-muted); font-size: 13px; grid-column: 1; }
.compact footer { grid-column: 2; grid-row: 2 / span 2; align-self: end; padding: 0; border: 0; }
.compact footer button { min-height: 44px; padding-inline: 10px; font-size: 13px; }
.compact .topline h4 { min-width: 0; }
.compact .product-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; padding-bottom: 2px; }
@media (max-width: 380px) { .compact footer { grid-column: 1 / -1; grid-row: auto; margin-top: 0; justify-content: flex-end; }.compact .facts { padding-right: 0; } }
</style>
