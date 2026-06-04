const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i

export function parseApiDate(value: string): Date {
  const normalized = HAS_TIMEZONE.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

export function formatApiDateTime(
  value: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return parseApiDate(value).toLocaleString('zh-CN', options)
}

export function formatApiTime(value: string): string {
  return parseApiDate(value).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}
