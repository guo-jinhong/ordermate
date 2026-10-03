<script setup lang="ts">
import { Minus, Plus, Trash2 } from '@lucide/vue'
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { finiteAmount, finitePositiveInteger, formatCurrency } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { CartRecord } from '../../types/results'

const props = withDefaults(defineProps<{ item: CartRecord; busy?: boolean; managing?: boolean }>(), { busy: false, managing: false })
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

// 商品详情使用 productId，数量和移除操作使用独立的 cartId。
const cartId = computed(() => finitePositiveInteger(props.item.cartId))
const productId = computed(() => finitePositiveInteger(props.item.productId))
const quantity = computed(() => finitePositiveInteger(props.item.quantity))
const price = computed(() => finiteAmount(props.item.price))
const subtotal = computed(() =>
  quantity.value != null && price.value != null ? quantity.value * price.value : null,
)
const productName = computed(() => props.item.productName?.trim() || '该商品')
// 数量以服务端返回为准，减少到一件后需通过“移除”操作删除。
const changeQuantity = (delta: number): void => {
  if (props.busy || cartId.value == null || quantity.value == null || quantity.value + delta < 1) return
  emit('prompt', { prompt: `将购物车项 ${cartId.value} 的数量改为 ${quantity.value + delta} 件`, displayPrompt: `将购物车中「${productName.value}」的数量改为 ${quantity.value + delta} 件`, label: '修改个人购物车', authRequired: true, preserveScroll: true })
}
</script>

<template>
  <!-- 紧凑商品行：名称查看详情，价格与数量并排。 -->
  <article class="cart-card">
    <button class="product-title" type="button" :disabled="busy || productId == null"
      @click="emit('prompt', { prompt: `查看商品 ${productId} 的详情`, displayPrompt: `查看「${productName}」的商品详情`, label: '查看商品详情', authRequired: false })">
      {{ customerCopy(item.productName || '商品名称待确认') }}
    </button>
    <div class="item-line">
      <p class="price">{{ formatCurrency(item.price) }} / 件
        <small v-if="quantity == null || quantity > 1">小计 {{ formatCurrency(subtotal, '金额待确认') }}</small>
      </p>
      <div class="quantity-control" :aria-label="`${productName}的数量`">
        <button type="button" :aria-label="`减少${productName}的数量`" :disabled="busy || cartId == null || quantity == null || quantity <= 1" @click="changeQuantity(-1)"><Minus :size="15" aria-hidden="true" /></button>
        <span>{{ quantity ?? '—' }}</span>
        <button type="button" :aria-label="`增加${productName}的数量`" :disabled="busy || cartId == null || quantity == null" @click="changeQuantity(1)"><Plus :size="15" aria-hidden="true" /></button>
      </div>
    </div>
    <button v-if="managing" class="danger" type="button" :disabled="busy || cartId == null"
      @click="emit('prompt', { prompt: `移除购物车项 ${cartId}`, displayPrompt: `从购物车移除「${productName}」`, label: '移出个人购物车商品', authRequired: true, preserveScroll: true })">
      <Trash2 :size="15" aria-hidden="true" />移除
    </button>
  </article>
</template>

<style scoped>
.cart-card { display: grid; gap: 4px; min-width: 0; padding: 12px 0; border-bottom: 1px solid var(--color-line); }
.product-title { padding: 0; color: var(--color-navy); background: transparent; border: 0; text-align: left; font-size: 16px; font-weight: 650; line-height: 1.45; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.product-title:hover:not(:disabled) { color: var(--color-primary-ink); text-decoration: underline; }
.item-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.price { min-width: 0; color: var(--color-muted); font-size: 13px; overflow-wrap: anywhere; }
.price small { display: block; font-size: 12px; }
.quantity-control { display: flex; align-items: center; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.quantity-control span { min-width: 24px; padding-inline: 2px; text-align: center; font-size: 14px; font-weight: 650; }
.quantity-control button { display: grid; place-items: center; width: 44px; height: 44px; padding: 0; color: var(--color-primary-ink); background: transparent; border: 0; border-radius: 8px; }
.quantity-control button:hover:not(:disabled) { background: var(--color-primary-soft); }
.danger { display: inline-flex; align-items: center; justify-self: end; gap: 4px; min-height: 44px; padding: 0 8px; color: var(--color-danger); background: transparent; border: 0; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
