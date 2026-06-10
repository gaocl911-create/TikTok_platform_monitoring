export function compactText(value: string | null | undefined) {
  return (value || '').replace(/\s+/g, ' ').trim()
}

export function uniqueSummary(title: string | null | undefined, summary: string | null | undefined) {
  const titleText = compactText(title)
  const summaryText = compactText(summary)

  if (!summaryText) return ''
  if (
    titleText &&
    (titleText === summaryText ||
      summaryText.startsWith(titleText) ||
      titleText.startsWith(summaryText))
  ) {
    return ''
  }
  return summaryText
}
