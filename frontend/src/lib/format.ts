const currencyFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  maximumFractionDigits: 0,
})

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export function finiteAmount(value: unknown): number | null {
  if (value == null || value === '') return null
  const amount = Number(value)
  return Number.isFinite(amount) && amount >= 0 ? amount : null
}

export function finitePositiveInteger(value: unknown): number | null {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isInteger(number) && number > 0 ? number : null
}

export function formatCurrency(value: unknown, fallback = '价格待确认'): string {
  const amount = finiteAmount(value)
  return amount == null ? fallback : currencyFormatter.format(amount)
}

export function formatDateTime(value: unknown, fallback = '时间待确认'): string {
  if (typeof value !== 'string' && typeof value !== 'number' && !(value instanceof Date)) {
    return fallback
  }
  if (value === '') return fallback

  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? fallback : dateTimeFormatter.format(date)
}
