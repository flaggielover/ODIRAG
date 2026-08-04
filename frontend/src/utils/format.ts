export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export function formatNumber(value: number | string | null | undefined, digits = 0): string {
  const numeric = Number(value ?? 0)
  if (!Number.isFinite(numeric)) return '-'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(numeric)
}

export function formatPercent(value: number | string | null | undefined, digits = 1): string {
  const numeric = Number(value ?? 0)
  if (!Number.isFinite(numeric)) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'percent',
    maximumFractionDigits: digits,
  }).format(numeric)
}

export function formatDuration(value: number | null | undefined): string {
  const milliseconds = Number(value ?? 0)
  if (!Number.isFinite(milliseconds)) return '-'
  if (milliseconds < 1000) return `${formatNumber(milliseconds, 0)} ms`
  return `${formatNumber(milliseconds / 1000, 2)} s`
}

export function formatCost(value: number | string | null | undefined): string {
  const numeric = Number(value ?? 0)
  if (!Number.isFinite(numeric)) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 6,
  }).format(numeric)
}

export function truncate(value: string, length = 120): string {
  return value.length > length ? `${value.slice(0, length)}...` : value
}
