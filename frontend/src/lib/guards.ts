import type { ToolCallRecord } from '@/types/api'
import type {
  CartRecord,
  OrderRecord,
  ProductRecord,
  ProductSearchContext,
  ResultKind,
  ResultPayload,
} from '@/types/results'

const CART_TOOLS = new Set([
  'get_cart',
  'add_to_cart',
  'update_cart',
  'update_cart_items',
  'remove_from_cart',
  'clear_cart',
])
const ORDER_TOOLS = new Set([
  'get_my_orders',
  'get_order_detail',
  'cancel_order',
  'refund_order',
  'create_order',
  'pay_order',
])
const PRODUCT_TOOLS = new Set(['search_products', 'get_product_detail'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasValue(record: Record<string, unknown>, key: string): boolean {
  return Object.hasOwn(record, key) && record[key] != null
}

function toolResultKind(name: string | undefined): ResultKind | null {
  if (!name) return null
  if (CART_TOOLS.has(name)) return 'cart'
  if (ORDER_TOOLS.has(name)) return 'order'
  if (PRODUCT_TOOLS.has(name)) return 'product'
  return null
}

export function normalizeResultRecords(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (isRecord(data) && Array.isArray(data.content)) return data.content
  return [data]
}

export function isOrderRecord(item: unknown): item is OrderRecord {
  return isRecord(item) && hasValue(item, 'orderNo')
}

export function isCartRecord(item: unknown): item is CartRecord {
  if (!isRecord(item) || hasValue(item, 'orderNo')) return false
  if (hasValue(item, 'cartId')) return true
  return (
    hasValue(item, 'productId') &&
    hasValue(item, 'quantity') &&
    typeof item.productName === 'string'
  )
}

export function isProductRecord(item: unknown): item is ProductRecord {
  if (!isRecord(item) || hasValue(item, 'orderNo')) return false
  const cartLike =
    hasValue(item, 'cartId') ||
    (hasValue(item, 'productId') &&
      hasValue(item, 'quantity') &&
      typeof item.productName === 'string')
  return !cartLike && typeof item.name === 'string' && Object.hasOwn(item, 'price')
}

function productContext(toolCalls: ToolCallRecord[]): ProductSearchContext {
  const call = [...toolCalls].reverse().find(({ name }) => PRODUCT_TOOLS.has(name))
  return call == null ? {} : { ...call.arguments }
}

function payloadForKnownKind(
  kind: ResultKind,
  records: unknown[],
  toolCalls: ToolCallRecord[],
): ResultPayload {
  if (records.length === 0) return { kind: 'empty', emptyKind: kind }
  if (kind === 'product') {
    return {
      kind,
      items: records.filter(isRecord) as ProductRecord[],
      context: productContext(toolCalls),
    }
  }
  if (kind === 'cart') return { kind, items: records.filter(isRecord) as CartRecord[] }
  return { kind, items: records.filter(isRecord) as OrderRecord[] }
}

export function resolveResultPayload(
  data: unknown,
  toolCalls: ToolCallRecord[],
): ResultPayload {
  if (data == null) return { kind: 'none' }

  const records = normalizeResultRecords(data)
  const lastNamedTool = toolCalls.at(-1)?.name
  const knownKind = toolResultKind(lastNamedTool)
  if (knownKind) return payloadForKnownKind(knownKind, records, toolCalls)

  const orders = records.filter(isOrderRecord)
  if (orders.length > 0) return { kind: 'order', items: orders }

  const cartItems = records.filter(isCartRecord)
  if (cartItems.length > 0) return { kind: 'cart', items: cartItems }

  const products = records.filter(isProductRecord)
  if (products.length > 0) return { kind: 'product', items: products, context: {} }

  return { kind: 'raw', value: data }
}
