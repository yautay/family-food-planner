export function roundNutrition(value) {
  if (!Number.isFinite(value)) {
    return 0
  }

  return Number(value.toFixed(2))
}

export function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

export function normalizeDate(value) {
  const date = normalizeText(value)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return null
  }

  return date
}

export function parseOptionalNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function parseOptionalInteger(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null
  }

  return parsed
}

export function parseRequiredPositiveInteger(value, fallback = null) {
  const parsed = parseOptionalInteger(value)
  if (parsed === null) {
    if (fallback !== null) {
      return fallback
    }

    throw new Error('Expected positive integer value')
  }

  return parsed
}
