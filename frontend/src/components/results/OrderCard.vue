<script setup lang="ts">
import { computed } from 'vue'

import { finiteAmount, formatCurrency, formatDateTime } from '../../lib/format'
import type { PromptAction } from '../../types/chat'
import type { OrderRecord } from '../../types/results'
import OrderItemRow from './OrderItemRow.vue'

const props = defineProps<{ order: OrderRecord }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const orderStatus = computed(() => {
  const value = props.order.status == null || props.order.status === ''
    ? Number.NaN
    : Number(props.order.status)
  const labels: Record<number, string> = {
    0: '待支付',
    1: '已支付',
    2: '已发货',
    3: '已完成',
    4: '已取消',
  }
  return {
    code: Number.isInteger(value) && value >= 0 && value <= 4 ? value : null,
    label: labels[value] ?? '未知状态',
  }
})
const paymentStatus = computed(() => {
  const value = props.order.paymentStatus == null || props.order.paymentStatus === ''
    ? Number.NaN
    : Number(props.order.paymentStatus)
  if (value === 0) return '未支付'
  if (value === 1) return '已支付'
  return '支付状态未知'
})
const amountLabel = computed(() => paymentStatus.value === '已支付' ? '实付金额' : '订单金额')
const totalAmount = computed(() => finiteAmount(props.order.totalAmount))
const discountAmount = computed(() => finiteAmount(props.order.discountAmount))
const finalAmount = computed(() =>
  finiteAmount(props.order.finalAmount) ?? totalAmount.value,
)
const orderLabel = computed(() => props.order.orderNo?.trim() || '当前订单')
</script>

<template>
  <article class="order-card">
    <header>
      <div><span>订单编号</span><strong>{{ order.orderNo || '订单号待确认' }}</strong></div>
      <span class="status" :data-status="orderStatus.code ?? 'unknown'">{{ orderStatus.label }}</span>
    </header>
    <div class="meta">
      <span>{{ order.createdAt ? `创建于 ${formatDateTime(order.createdAt)}` : '创建时间待确认' }}</span>
      <span>{{ paymentStatus }}</span>
    </div>
    <div class="items">
      <OrderItemRow v-for="(item, index) in order.items ?? []" :key="String(item.productId ?? index)" :item="item" />
      <p v-if="!order.items?.length">暂无商品明细</p>
    </div>
    <dl class="amounts">
      <div v-if="totalAmount != null"><dt>商品总额</dt><dd>{{ formatCurrency(totalAmount) }}</dd></div>
      <div v-if="discountAmount != null && discountAmount > 0"><dt>优惠</dt><dd>-{{ formatCurrency(discountAmount) }}</dd></div>
      <div class="final"><dt>{{ amountLabel }}</dt><dd>{{ formatCurrency(finalAmount, '金额待确认') }}</dd></div>
    </dl>
    <footer>
      <button
        type="button"
        :disabled="order.id == null"
        @click="emit('prompt', {
          prompt: `查看订单 ${order.id} 的详情`,
          displayPrompt: `查看订单 ${orderLabel} 的详情`,
          label: '查看本人订单详情',
          authRequired: true,
        })"
      >
        查看详情
      </button>
      <button
        v-if="orderStatus.code === 0 && order.id != null"
        class="danger"
        type="button"
        @click="emit('prompt', {
          prompt: `取消订单 ${order.id}`,
          displayPrompt: `取消订单 ${orderLabel}`,
          label: '取消本人订单',
          authRequired: true,
        })"
      >
        取消订单
      </button>
    </footer>
  </article>
</template>

<style scoped>
.order-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
header, .meta, footer, .amounts div { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }header > div { display: grid; gap: var(--space-1); }header > div span, .meta, .items > p, .amounts dt { color: var(--color-muted); font-size: var(--text-sm); }header strong { color: var(--color-navy); }
.status { padding: var(--space-1) var(--space-2); color: var(--color-muted); background: var(--color-surface-subtle); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 800; }.status[data-status="0"] { color: var(--color-warning); background: var(--color-warning-soft); }.status[data-status="1"], .status[data-status="2"], .status[data-status="3"] { color: var(--color-success); background: var(--color-success-soft); }.status[data-status="4"] { color: var(--color-danger); background: var(--color-danger-soft); }
.items { padding: var(--space-2) var(--space-3); background: var(--color-surface-subtle); border-radius: var(--radius-md); }.items > p { padding-block: var(--space-2); }
.amounts { display: grid; gap: var(--space-2); margin: 0; }.amounts dd { margin: 0; font-weight: 700; }.amounts .final { padding-top: var(--space-2); border-top: 1px solid var(--color-line); }.amounts .final dd { color: var(--color-primary-ink); font-size: var(--text-lg); }
footer { justify-content: flex-end; }button { min-height: var(--control-height-md); padding-inline: var(--space-4); color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); font-weight: 700; }.danger { color: var(--color-danger); border-color: var(--color-danger); }button:disabled { opacity: 0.5; }
@media (max-width: 680px) { header, .meta { align-items: flex-start; flex-direction: column; }footer button { flex: 1; } }
</style>
