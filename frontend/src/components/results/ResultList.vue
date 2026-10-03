<script setup lang="ts">
import { ChevronDown, RefreshCw } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'
import EmptyResult from './EmptyResult.vue'
import CartCard from './CartCard.vue'
import CartSummary from './CartSummary.vue'
import OrderCard from './OrderCard.vue'
import ProductCard from './ProductCard.vue'
import RawResult from './RawResult.vue'
import type { PromptAction } from '../../types/chat'
import type { ResultPayload } from '../../types/results'

const props = withDefaults(defineProps<{ payload: ResultPayload; busy?: boolean }>(), { busy: false })
// 商品分批展开，避免一次返回大量结果挤满对话。
const titleId = useId()
const visibleCount = ref(4)
const managing = ref(false)
const cartExpanded = ref(false)
const summaryExpanded = ref(false)
watch(() => props.payload, (next, previous) => {
  if (next.kind === 'cart' && previous?.kind === 'cart' && next.preserveState) return
  visibleCount.value = 4
  managing.value = false
  cartExpanded.value = false
  summaryExpanded.value = false
})
const visibleCart = computed(() => props.payload.kind === 'cart' ? props.payload.items.slice(0, cartExpanded.value ? undefined : 4) : [])
const summaryOnly = computed(() => 'summaryOnly' in props.payload && props.payload.summaryOnly && !summaryExpanded.value)
const visibleProducts = computed(() => props.payload.kind === 'product' ? props.payload.items.slice(0, visibleCount.value) : [])
const emit = defineEmits<{ prompt: [action: PromptAction] }>()
</script>

<template>
  <section
    v-if="payload.kind === 'product'"
    class="result-list"
    data-result-kind="product"
    :aria-labelledby="summaryOnly ? undefined : titleId"
    :aria-label="summaryOnly ? '商品统计明细' : undefined"
  >
    <header v-if="!summaryOnly">
      <h3 :id="titleId">商品结果</h3>
      <span>{{ payload.items.length }} 项</span>
    </header>
    <div v-if="!summaryOnly" class="card-grid product-grid" :class="{ single: payload.items.length === 1 }">
      <ProductCard
        v-for="(item, index) in visibleProducts"
        :key="String(item.id ?? index)"
        :product="item"
        :context="payload.context"
        :compact="payload.context.detail !== true"
        :busy="busy"
        @prompt="emit('prompt', $event)"
      />
    </div>
    <button v-if="summaryOnly" class="summary-link" type="button" @click="summaryExpanded = true">查看商品</button>
    <div v-if="!summaryOnly && payload.items.length > 4" class="result-pagination">
      <span role="status">已显示 {{ visibleProducts.length }} / {{ payload.items.length }} 件</span>
      <button v-if="visibleProducts.length < payload.items.length" type="button" @click="visibleCount += 4"><ChevronDown :size="16" aria-hidden="true" />再显示 {{ Math.min(4, payload.items.length - visibleProducts.length) }} 件</button>
    </div>
  </section>

  <section
    v-else-if="payload.kind === 'cart'"
    class="result-list"
    data-result-kind="cart"
    :aria-labelledby="titleId"
  >
    <!-- 汇总始终按完整购物车计算，折叠只影响商品行。 -->
    <header>
      <h3 :id="titleId">购物车</h3>
      <div class="result-tools">
        <button type="button" :disabled="busy" @click="emit('prompt', { prompt: '查看我的购物车', label: '刷新个人购物车', authRequired: true, preserveScroll: true })"><RefreshCw :size="14" aria-hidden="true" />刷新</button>
        <button v-if="!summaryOnly" type="button" :aria-pressed="managing" @click="managing = !managing">{{ managing ? '完成' : '管理' }}</button>
      </div>
    </header>
    <p v-if="payload.feedback" class="cart-feedback" role="status">{{ customerCopy(payload.feedback) }}</p>
    <CartSummary :items="payload.items" :busy="busy" :managing="managing && !summaryOnly && !payload.stale" @prompt="emit('prompt', $event)" />
    <button v-if="summaryOnly" class="summary-link" type="button" @click="summaryExpanded = true">查看购物车明细</button>
    <div v-else class="cart-rows">
      <CartCard v-for="(item, index) in visibleCart" :key="String(item.cartId ?? index)" :item="item" :busy="busy || !!payload.stale" :managing="managing" @prompt="emit('prompt', $event)" />
      <button v-if="payload.items.length > 4" class="summary-link" type="button" :aria-expanded="cartExpanded" @click="cartExpanded = !cartExpanded">{{ cartExpanded ? '收起' : `查看全部${payload.items.length}种商品` }}</button>
    </div>
  </section>

  <section
    v-else-if="payload.kind === 'order'"
    class="result-list"
    data-result-kind="order"
    :aria-labelledby="titleId"
  >
    <header>
      <h3 :id="titleId">订单结果</h3>
      <span>{{ payload.items.length }} 项</span>
    </header>
    <div class="card-grid">
      <OrderCard
        v-for="(item, index) in payload.items"
        :key="String(item.id ?? item.orderNo ?? index)"
        :order="item" :busy="busy"
        @prompt="emit('prompt', $event)"
      />
    </div>
  </section>

  <EmptyResult
    v-else-if="payload.kind === 'empty'"
    :kind="payload.emptyKind"
    @prompt="emit('prompt', $event)"
  />
  <RawResult v-else-if="payload.kind === 'raw'" :value="payload.value" />
</template>

<style scoped>
.result-list {
  display: grid;
  gap: var(--space-3);
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

h3 {
  color: var(--color-navy);
  font-size: var(--text-lg);
}

header span {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.identity-list,
.card-grid {
  display: grid;
  gap: var(--space-3);
}

.identity-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.identity-list li {
  padding: var(--space-3);
  color: var(--color-ink);
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}
/* 白色单品卡片与浅灰页面区分，宽屏两列、窄屏单列。 */
.product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.product-grid.single { grid-template-columns: minmax(0, 1fr); }
.result-pagination { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding-top: var(--space-2); color: var(--color-muted); font-size: var(--text-sm); }
.result-pagination button, .result-tools button { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height-sm); padding: var(--space-2) var(--space-3); color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-sm); }
.result-tools { display: flex; align-items: center; gap: 4px; }
@media (max-width: 680px) { .product-grid { grid-template-columns: minmax(0, 1fr); } }
/* 单面板承载汇总和清单，减少嵌套卡片。 */
.result-list[data-result-kind="cart"] { gap: 0; padding: 12px 16px; background: var(--color-surface); border: 1px solid var(--color-line); border-radius: 12px; }
.result-tools button { min-height: 44px; padding: 0 8px; background: transparent; border: 0; }
.summary-link { min-height: 44px; padding: 8px; color: var(--color-primary-ink); background: transparent; border: 0; text-align: center; }
.cart-rows { display: grid; min-width: 0; }
.cart-feedback { padding: 4px 0; color: var(--color-muted); font-size: 13px; overflow-wrap: anywhere; }
</style>
