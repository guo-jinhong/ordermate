<script setup lang="ts">
import EmptyResult from './EmptyResult.vue'
import CartCard from './CartCard.vue'
import CartSummary from './CartSummary.vue'
import OrderCard from './OrderCard.vue'
import ProductCard from './ProductCard.vue'
import RawResult from './RawResult.vue'
import type { PromptAction } from '../../types/chat'
import type { ResultPayload } from '../../types/results'

defineProps<{ payload: ResultPayload }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()
</script>

<template>
  <section
    v-if="payload.kind === 'product'"
    class="result-list"
    data-result-kind="product"
    aria-labelledby="product-results-title"
  >
    <header>
      <h3 id="product-results-title">商品结果</h3>
      <span>{{ payload.items.length }} 项</span>
    </header>
    <div class="card-grid">
      <ProductCard
        v-for="(item, index) in payload.items"
        :key="String(item.id ?? index)"
        :product="item"
        :context="payload.context"
        @prompt="emit('prompt', $event)"
      />
    </div>
  </section>

  <section
    v-else-if="payload.kind === 'cart'"
    class="result-list"
    data-result-kind="cart"
    aria-labelledby="cart-results-title"
  >
    <header>
      <h3 id="cart-results-title">购物车结果</h3>
      <span>{{ payload.items.length }} 项</span>
    </header>
    <div class="card-grid">
      <CartCard
        v-for="(item, index) in payload.items"
        :key="String(item.cartId ?? index)"
        :item="item"
        @prompt="emit('prompt', $event)"
      />
      <CartSummary :items="payload.items" @prompt="emit('prompt', $event)" />
    </div>
  </section>

  <section
    v-else-if="payload.kind === 'order'"
    class="result-list"
    data-result-kind="order"
    aria-labelledby="order-results-title"
  >
    <header>
      <h3 id="order-results-title">订单结果</h3>
      <span>{{ payload.items.length }} 项</span>
    </header>
    <div class="card-grid">
      <OrderCard
        v-for="(item, index) in payload.items"
        :key="String(item.id ?? item.orderNo ?? index)"
        :order="item"
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
  gap: var(--space-2);
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
</style>
