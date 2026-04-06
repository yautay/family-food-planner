import catalogDb from '../db/catalog.js'

const MASS_ALIASES = new Map([
  ['mg', { symbol: 'mg', toGrams: 0.001 }],
  ['g', { symbol: 'g', toGrams: 1 }],
  ['gram', { symbol: 'g', toGrams: 1 }],
  ['gramy', { symbol: 'g', toGrams: 1 }],
  ['dag', { symbol: 'dag', toGrams: 10 }],
  ['kg', { symbol: 'kg', toGrams: 1000 }],
  ['kilogram', { symbol: 'kg', toGrams: 1000 }],
  ['kilogramy', { symbol: 'kg', toGrams: 1000 }],
])

const VOLUME_ALIASES = new Map([
  ['ml', { symbol: 'ml', toMl: 1 }],
  ['mililitr', { symbol: 'ml', toMl: 1 }],
  ['mililitry', { symbol: 'ml', toMl: 1 }],
  ['l', { symbol: 'l', toMl: 1000 }],
  ['litr', { symbol: 'l', toMl: 1000 }],
  ['litry', { symbol: 'l', toMl: 1000 }],
])

function normalizeNameForCheck(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}

function inferPhysicalUnit(name) {
  const normalized = normalizeNameForCheck(name)

  if (MASS_ALIASES.has(normalized)) {
    const mass = MASS_ALIASES.get(normalized)
    return {
      unitType: 'mass',
      symbol: mass.symbol,
      toGramsFactor: mass.toGrams,
      toMlFactor: null,
    }
  }

  if (VOLUME_ALIASES.has(normalized)) {
    const volume = VOLUME_ALIASES.get(normalized)
    return {
      unitType: 'volume',
      symbol: volume.symbol,
      toGramsFactor: null,
      toMlFactor: volume.toMl,
    }
  }

  return null
}

function ensurePhysicalUnitName(name) {
  const physical = inferPhysicalUnit(name)
  if (!physical) {
    throw new Error('Units are only mass/volume (for example mg, g, dag, kg, ml, l).')
  }

  return physical
}

async function getUnits() {
  return catalogDb
    .prepare(
      `
      SELECT
        id,
        name,
        symbol,
        unit_type,
        to_grams_factor,
        to_ml_factor
      FROM units
      WHERE unit_type IN ('mass', 'volume')
      ORDER BY name COLLATE NOCASE ASC
      `,
    )
    .all()
}

async function addUnit(unit) {
  const name = typeof unit?.name === 'string' ? unit.name.trim() : ''
  if (!name) {
    throw new Error('Unit name is required')
  }

  const physical = ensurePhysicalUnitName(name)

  const result = catalogDb
    .prepare(
      `
      INSERT INTO units(name, symbol, unit_type, to_grams_factor, to_ml_factor)
      VALUES (?, ?, ?, ?, ?)
      `,
    )
    .run(name, physical.symbol, physical.unitType, physical.toGramsFactor, physical.toMlFactor)

  return catalogDb
    .prepare(
      `
      SELECT
        id,
        name,
        symbol,
        unit_type,
        to_grams_factor,
        to_ml_factor
      FROM units
      WHERE id = ?
      `,
    )
    .get(Number(result.lastInsertRowid))
}

async function updateUnit(unit) {
  const unitId = Number(unit?.id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit id is invalid')
  }

  const existing = catalogDb.prepare('SELECT id FROM units WHERE id = ?').get(unitId)
  if (!existing) {
    return 0
  }

  const name = typeof unit?.name === 'string' ? unit.name.trim() : ''
  if (!name) {
    throw new Error('Unit name is required')
  }

  const physical = ensurePhysicalUnitName(name)

  return catalogDb
    .prepare(
      `
      UPDATE units
      SET
        name = ?,
        symbol = ?,
        unit_type = ?,
        to_grams_factor = ?,
        to_ml_factor = ?
      WHERE id = ?
      `,
    )
    .run(
      name,
      physical.symbol,
      physical.unitType,
      physical.toGramsFactor,
      physical.toMlFactor,
      unitId,
    ).changes
}

async function deleteUnit(id) {
  const unitId = Number(id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit id is invalid')
  }

  return catalogDb.prepare('DELETE FROM units WHERE id = ?').run(unitId).changes
}

export default {
  getUnits,
  addUnit,
  updateUnit,
  deleteUnit,
}
