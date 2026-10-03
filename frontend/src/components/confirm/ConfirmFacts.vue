<script setup lang="ts">
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import type { ConfirmationAction } from '../../types/api'

interface Fact {
  label: string
  value: string
}

const props = defineProps<{
  action: ConfirmationAction | string
  args: Record<string, unknown>
}>()

const display = (value: unknown, fallback = '待确认'): string =>
  value == null || value === '' ? fallback : String(value)

const facts = computed<Fact[]>(() => {
  const args = props.args
  switch (props.action) {
    case 'cancel_order':
      return [{ label: '订单', value: display(args.order_no, '当前订单') }]
    case 'refund_order':
      return [
        { label: '订单', value: display(args.order_no, '当前订单') },
        ...(args.reason ? [{ label: '退款原因', value: display(args.reason) }] : []),
      ]
    case 'update_cart':
      return [
        { label: '商品', value: display(args.product_name, '购物车中的商品') },
        { label: '修改后数量', value: display(args.quantity) },
      ]
    case 'update_cart_items': {
      const items = Array.isArray(args.items) ? args.items : []
      return [
        { label: '涉及商品', value: items.length ? `${items.length} 种商品` : '数量待确认' },
        { label: '修改后数量', value: display(args.quantity) },
      ]
    }
    case 'remove_from_cart':
      return [{ label: '商品', value: display(args.product_name, '购物车中的商品') }]
    case 'clear_cart':
      return [{ label: '涉及商品', value: '当前购物车全部商品' }]
    case 'create_order':
      return [
        { label: '商品', value: display(args.product_name, '该商品') },
        { label: '数量', value: display(args.quantity) },
        { label: '收货地址', value: display(args.address_summary, '当前账号的收货地址') },
        ...(args.payment_method
          ? [{ label: '支付方式', value: display(args.payment_method) }]
          : []),
      ]
    case 'pay_order':
      return [{ label: '订单', value: display(args.order_no, '当前订单') }]
    default:
      return [{ label: '涉及商品', value: '请查看上方操作内容' }]
  }
})
</script>

<template>
  <dl class="facts">
    <div v-for="fact in facts" :key="fact.label">
      <dt>{{ fact.label }}</dt>
      <dd>{{ customerCopy(fact.value) }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); margin: 0; }.facts div { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-surface-subtle); border: 1px solid var(--color-line); border-radius: var(--radius-md); }.facts dt { color: var(--color-muted); font-size: var(--text-xs); }.facts dd { margin: 0; color: var(--color-navy); font-weight: 800; overflow-wrap: anywhere; }
@media (max-width: 680px) { .facts { grid-template-columns: 1fr; } }
</style>
