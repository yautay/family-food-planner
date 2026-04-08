const PHYSICAL_UNITS = new Set([
  'mg',
  'g',
  'gram',
  'gramy',
  'dag',
  'kg',
  'kilogram',
  'kilogramy',
  'ml',
  'mililitr',
  'mililitry',
  'l',
  'litr',
  'litry',
])

export function normalizeUnitName(value) {
  return String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

export function isPhysicalUnit(unitName) {
  return Boolean(unitName) && PHYSICAL_UNITS.has(normalizeUnitName(unitName))
}

export function shouldHideDefaultPhysicalQuantity(ingredient) {
  const unit = ingredient?.unit_name ? String(ingredient.unit_name).trim() : ''
  const numericQuantity = Number(ingredient?.quantity)
  const noPackageMapping = !ingredient?.ingredient_package_conversion_id

  return (
    noPackageMapping &&
    isPhysicalUnit(unit) &&
    Number.isFinite(numericQuantity) &&
    numericQuantity === 1
  )
}

export function formatIngredientAmount(ingredient) {
  const unit = ingredient?.unit_name ? String(ingredient.unit_name).trim() : ''
  const hasQuantity = ingredient?.quantity !== null && ingredient?.quantity !== undefined

  if (hasQuantity) {
    if (shouldHideDefaultPhysicalQuantity(ingredient)) {
      return unit || '-'
    }

    return unit ? `${ingredient.quantity} ${unit}` : String(ingredient.quantity)
  }

  return unit || '-'
}
