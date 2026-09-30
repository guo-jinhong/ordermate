import type { ConfirmationAction, ToolOutcome } from '@/types/api'
import type { MessageStatusTone } from '@/types/chat'
import type { ResultKind } from '@/types/results'
import type { StreamEvent } from '@/types/stream'

export interface ToolStatusCopy {
  message: string
  status: string
  tone: MessageStatusTone
}

export interface ConfirmationPresentation {
  title: string
  icon: string
  badge: string
  tone: 'primary' | 'warning' | 'danger'
  confirmLabel: string
  impact: string
}

export interface EmptyResultCopy {
  title: string
  description: string
  actionLabel: string
}

const TOOL_LABELS: Record<string, string> = {
  search_knowledge_base: '查询业务规则',
  search_products: '筛选商品',
  get_product_detail: '读取商品详情',
  get_cart: '读取购物车',
  add_to_cart: '添加购物车商品',
  update_cart: '更新购物车',
  update_cart_items: '批量更新购物车',
  remove_from_cart: '移除购物车商品',
  clear_cart: '清空购物车',
  get_my_orders: '查询订单',
  get_order_detail: '读取订单详情',
  cancel_order: '取消订单',
  refund_order: '申请订单退款',
  create_order: '创建订单',
  pay_order: '支付订单',
}

const STREAM_EVENT_LABELS: Record<StreamEvent['type'], string> = {
  started: '开始处理',
  progress: '处理进度',
  llm_trace: '模型调用',
  reference: '上下文引用',
  clarification: '需要补充信息',
  tool_error: '业务步骤失败',
  tool: '业务步骤',
  confirmation_required: '等待用户确认',
  result: '生成结果',
  error: '运行失败',
}

const CONFIRMATION_PRESENTATIONS: Record<ConfirmationAction, ConfirmationPresentation> = {
  cancel_order: {
    title: '取消这笔订单？', icon: '!', badge: '高风险', tone: 'danger',
    confirmLabel: '确认取消订单',
    impact: '订单将变为已取消，之后不能继续支付；如仍需购买，需要重新下单。',
  },
  refund_order: {
    title: '提交退款申请？', icon: '¥', badge: '高风险', tone: 'danger',
    confirmLabel: '确认申请退款',
    impact: '系统将提交退款申请，后续结果以订单售后状态为准。',
  },
  update_cart: {
    title: '修改购物车数量？', icon: '±', badge: '将修改数据', tone: 'warning',
    confirmLabel: '确认修改数量', impact: '购物车中的商品数量和合计金额将随之变化。',
  },
  update_cart_items: {
    title: '批量修改购物车？', icon: '±', badge: '批量修改', tone: 'warning',
    confirmLabel: '确认批量修改', impact: '多个购物车项的数量和合计金额将同时发生变化。',
  },
  remove_from_cart: {
    title: '移除这件商品？', icon: '−', badge: '将删除数据', tone: 'danger',
    confirmLabel: '确认移除', impact: '该商品将从购物车移除；需要时可以重新搜索并添加。',
  },
  clear_cart: {
    title: '清空整个购物车？', icon: '!', badge: '高风险', tone: 'danger',
    confirmLabel: '确认清空购物车',
    impact: '当前购物车中的所有商品都会被移除，需要时必须重新添加。',
  },
  create_order: {
    title: '创建这笔订单？', icon: '+', badge: '将创建数据', tone: 'primary',
    confirmLabel: '确认创建订单',
    impact: '系统将使用演示地址和支付方式创建新订单，创建后仍需完成支付。',
  },
  pay_order: {
    title: '确认支付这笔订单？', icon: '¥', badge: '高风险', tone: 'danger',
    confirmLabel: '确认演示支付',
    impact: '订单支付状态将发生变化。本项目使用演示支付，不会发起真实扣款。',
  },
}

const GENERIC_CONFIRMATION_PRESENTATION: ConfirmationPresentation = {
  title: '确认执行这项操作？',
  icon: '!',
  badge: '需要确认',
  tone: 'warning',
  confirmLabel: '确认执行',
  impact: '系统只会在你明确确认后执行这项操作。',
}

const EMPTY_RESULT_COPY: Record<ResultKind, EmptyResultCopy> = {
  product: {
    title: '没有找到匹配商品', description: '可以调整关键词或价格范围后重新搜索。',
    actionLabel: '重新搜索商品',
  },
  cart: {
    title: '购物车还是空的', description: '先搜索商品，再选择需要加入购物车的商品。',
    actionLabel: '去搜索商品',
  },
  order: {
    title: '暂时没有订单', description: '创建订单后，可以在这里查询状态和详情。',
    actionLabel: '去查看商品',
  },
}

export function toolBusinessLabel(name: string): string {
  return TOOL_LABELS[name] ?? '调用业务工具'
}

export function streamEventLabel(type: StreamEvent['type']): string {
  return STREAM_EVENT_LABELS[type]
}

export function toolStatusCopy(name: string, outcome: ToolOutcome): ToolStatusCopy {
  const label = toolBusinessLabel(name)
  if (outcome === 'error') return { message: `${label}未完成`, status: '执行失败', tone: 'error' }
  if (outcome === 'clarification_needed') {
    return { message: `${label}需要补充信息`, status: '等待补充', tone: 'warning' }
  }
  return { message: `${label}已完成`, status: '执行成功', tone: 'success' }
}

export function confirmationPresentation(action: string): ConfirmationPresentation {
  return CONFIRMATION_PRESENTATIONS[action as ConfirmationAction] ?? GENERIC_CONFIRMATION_PRESENTATION
}

export function emptyResultCopy(kind: ResultKind): EmptyResultCopy {
  return EMPTY_RESULT_COPY[kind]
}
