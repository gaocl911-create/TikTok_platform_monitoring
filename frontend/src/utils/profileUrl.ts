const URL_PATTERN = /https?:\/\/[^\s<>"']+/i
const TRAILING_SHARE_PUNCTUATION = /[，。！？；：、,.;!?\])}】》”’]+$/
const DOUYIN_SHARE_HOSTS = new Set(['v.douyin.com', 'iesdouyin.com', 'www.iesdouyin.com'])

export function normalizeProfileUrl(value: string): string {
  const trimmed = value.trim()
  const match = trimmed.match(URL_PATTERN)
  if (!match?.[0]) return trimmed

  const normalized = match[0].replace(TRAILING_SHARE_PUNCTUATION, '')
  try {
    const url = new URL(normalized)
    const isShareText = (match.index || 0) > 0 || DOUYIN_SHARE_HOSTS.has(url.hostname)
    return /\s/.test(trimmed) && !isShareText ? trimmed : normalized
  } catch {
    return trimmed
  }
}

export function isValidProfileUrl(value: string): boolean {
  const normalized = normalizeProfileUrl(value)
  if (/\s/.test(normalized)) return false
  try {
    const url = new URL(normalized)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}
