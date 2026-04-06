import catalogDb from '../db/catalog.js'

function normalizeName(name) {
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

function parsePositiveNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function resolvePackageTypeId(payload) {
  const packageTypeId = Number(payload?.package_type_id)
  if (Number.isInteger(packageTypeId) && packageTypeId > 0) {
    return packageTypeId
  }

  const packageTypeName =
    typeof payload?.package_type_name === 'string' ? payload.package_type_name.trim() : ''

  if (!packageTypeName) {
    throw new Error('Package type is required')
  }

  const normalizedName = normalizeName(packageTypeName)
  const existing = catalogDb
    .prepare('SELECT id FROM package_types WHERE normalized_name = ?')
    .get(normalizedName)

  if (existing) {
    return existing.id
  }

  const created = catalogDb
    .prepare('INSERT INTO package_types(name, normalized_name) VALUES (?, ?)')
    .run(packageTypeName, normalizedName)

  return Number(created.lastInsertRowid)
}

function getConversionById(conversionId) {
  return catalogDb
    .prepare(
      `
      SELECT
        ipc.id,
        ipc.product_id,
        p.name AS product_name,
        ipc.package_type_id,
        pt.name AS package_type_name,
        ipc.grams_per_package,
        ipc.samples_count,
        ipc.source,
        ipc.created_at,
        ipc.updated_at
      FROM ingredient_package_conversions ipc
      INNER JOIN products p ON p.id = ipc.product_id
      INNER JOIN package_types pt ON pt.id = ipc.package_type_id
      WHERE ipc.id = ?
      `,
    )
    .get(conversionId)
}

async function getPackageTypes() {
  return catalogDb
    .prepare(
      `
      SELECT
        id,
        name,
        normalized_name
      FROM package_types
      ORDER BY name COLLATE NOCASE ASC
      `,
    )
    .all()
}

async function getPackages() {
  return catalogDb
    .prepare(
      `
      SELECT
        ipc.id,
        ipc.product_id,
        p.name AS product_name,
        ipc.package_type_id,
        pt.name AS package_type_name,
        ipc.grams_per_package,
        ipc.samples_count,
        ipc.source,
        ipc.created_at,
        ipc.updated_at
      FROM ingredient_package_conversions ipc
      INNER JOIN products p ON p.id = ipc.product_id
      INNER JOIN package_types pt ON pt.id = ipc.package_type_id
      ORDER BY p.name COLLATE NOCASE ASC, pt.name COLLATE NOCASE ASC
      `,
    )
    .all()
}

async function addPackage(payload) {
  const productId = Number(payload?.product_id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient is required')
  }

  const gramsPerPackage = parsePositiveNumber(payload?.grams_per_package)
  if (gramsPerPackage === null) {
    throw new Error('grams_per_package must be a positive number')
  }

  const packageTypeId = resolvePackageTypeId(payload)
  const source = typeof payload?.source === 'string' ? payload.source.trim() : 'manual'

  const existing = catalogDb
    .prepare(
      `
      SELECT id
      FROM ingredient_package_conversions
      WHERE product_id = ? AND package_type_id = ?
      `,
    )
    .get(productId, packageTypeId)

  if (existing) {
    catalogDb
      .prepare(
        `
        UPDATE ingredient_package_conversions
        SET
          grams_per_package = ?,
          source = ?,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        `,
      )
      .run(gramsPerPackage, source || 'manual', existing.id)

    return getConversionById(existing.id)
  }

  const created = catalogDb
    .prepare(
      `
      INSERT INTO ingredient_package_conversions(
        product_id,
        package_type_id,
        grams_per_package,
        source,
        samples_count
      )
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(productId, packageTypeId, gramsPerPackage, source || 'manual', 1)

  return getConversionById(Number(created.lastInsertRowid))
}

async function updatePackage(payload) {
  const conversionId = Number(payload?.id)
  if (!Number.isInteger(conversionId) || conversionId <= 0) {
    throw new Error('Package mapping id is invalid')
  }

  const existing = catalogDb
    .prepare('SELECT id FROM ingredient_package_conversions WHERE id = ?')
    .get(conversionId)

  if (!existing) {
    return 0
  }

  const productId = Number(payload?.product_id)
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error('Ingredient is required')
  }

  const gramsPerPackage = parsePositiveNumber(payload?.grams_per_package)
  if (gramsPerPackage === null) {
    throw new Error('grams_per_package must be a positive number')
  }

  const packageTypeId = resolvePackageTypeId(payload)
  const source = typeof payload?.source === 'string' ? payload.source.trim() : 'manual'

  return catalogDb
    .prepare(
      `
      UPDATE ingredient_package_conversions
      SET
        product_id = ?,
        package_type_id = ?,
        grams_per_package = ?,
        source = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
      `,
    )
    .run(productId, packageTypeId, gramsPerPackage, source || 'manual', conversionId).changes
}

async function deletePackage(conversionId) {
  const id = Number(conversionId)
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error('Package mapping id is invalid')
  }

  const usage = catalogDb
    .prepare(
      'SELECT COUNT(*) AS count FROM recipe_ingredients WHERE ingredient_package_conversion_id = ?',
    )
    .get(id)

  if ((usage?.count ?? 0) > 0) {
    throw new Error('Package mapping is used in recipes and cannot be deleted')
  }

  return catalogDb.prepare('DELETE FROM ingredient_package_conversions WHERE id = ?').run(id)
    .changes
}

export default {
  getPackageTypes,
  getPackages,
  addPackage,
  updatePackage,
  deletePackage,
}
