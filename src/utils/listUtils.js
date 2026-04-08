export function normalizeSearchText(value) {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

export function filterBySearch(items, searchValue, searchableResolver) {
  const needle = normalizeSearchText(searchValue)

  if (!needle) {
    return [...items]
  }

  return items.filter((item) => {
    const searchable = searchableResolver(item)
    return normalizeSearchText(searchable).includes(needle)
  })
}

export function sortByField(items, sortBy, sortDirection = 'asc', resolvers = {}) {
  const direction = sortDirection === 'desc' ? -1 : 1
  const resolveValue =
    typeof resolvers?.[sortBy] === 'function' ? resolvers[sortBy] : (item) => item?.[sortBy] ?? ''

  return [...items].sort((left, right) => {
    const leftValue = resolveValue(left)
    const rightValue = resolveValue(right)

    const leftNumber = Number(leftValue)
    const rightNumber = Number(rightValue)
    const numbersComparable = Number.isFinite(leftNumber) && Number.isFinite(rightNumber)

    if (numbersComparable) {
      if (leftNumber === rightNumber) {
        return 0
      }

      return leftNumber > rightNumber ? direction : -direction
    }

    return (
      String(leftValue).localeCompare(String(rightValue), undefined, {
        sensitivity: 'base',
        numeric: true,
      }) * direction
    )
  })
}
