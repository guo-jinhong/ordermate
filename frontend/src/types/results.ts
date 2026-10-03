export interface ProductRecord {
  id?: number | string | null
  name?: string | null
  price?: number | string | null
  stock?: number | string | null
  status?: number | string | null
  description?: string | null
  categoryId?: number | string | null
}

export interface CartRecord {
  cartId?: number | string | null
  productId?: number | string | null
  productName?: string | null
  price?: number | string | null
  quantity?: number | string | null
}

export interface OrderItemRecord {
  productId?: number | string | null
  productName?: string | null
  quantity?: number | string | null
  unitPrice?: number | string | null
  totalPrice?: number | string | null
}

export interface OrderRecord {
  id?: number | string | null
  orderNo?: string | null
  status?: number | string | null
  paymentStatus?: number | string | null
  createdAt?: string | null
  items?: OrderItemRecord[]
  totalAmount?: number | string | null
  discountAmount?: number | string | null
  finalAmount?: number | string | null
}

/** 商品搜索的匹配依据，来自 search_products / get_product_detail 的入参。 */
export interface ProductSearchContext {
  keyword?: string
  max_price?: number | string
  min_price?: number | string
  in_stock?: boolean
  [key: string]: unknown
}

export type ResultKind = 'product' | 'cart' | 'order'

export type ResultPayload =
  | { kind: 'product'; items: ProductRecord[]; context: ProductSearchContext; summaryOnly?: boolean }
  | { kind: 'cart'; items: CartRecord[]; summaryOnly?: boolean; preserveState?: boolean; stale?: boolean; feedback?: string }
  | { kind: 'order'; items: OrderRecord[] }
  | { kind: 'empty'; emptyKind: ResultKind }
  | { kind: 'raw'; value: unknown }
  | { kind: 'none' }
