import { Op, literal } from 'sequelize'
import models from '../models/index.js'

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
  return models.unit.findAll({
    attributes: ['id', 'name', 'symbol', 'unit_type', 'to_grams_factor', 'to_ml_factor'],
    where: {
      unit_type: {
        [Op.in]: ['mass', 'volume'],
      },
    },
    order: [[literal('name COLLATE NOCASE'), 'ASC']],
    raw: true,
  })
}

async function addUnit(unit) {
  const name = typeof unit?.name === 'string' ? unit.name.trim() : ''
  if (!name) {
    throw new Error('Unit name is required')
  }

  const physical = ensurePhysicalUnitName(name)

  const created = await models.unit.create({
    name,
    symbol: physical.symbol,
    unit_type: physical.unitType,
    to_grams_factor: physical.toGramsFactor,
    to_ml_factor: physical.toMlFactor,
  })

  return created.get({ plain: true })
}

async function updateUnit(unit) {
  const unitId = Number(unit?.id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit id is invalid')
  }

  const existing = await models.unit.findByPk(unitId, { attributes: ['id'] })
  if (!existing) {
    return 0
  }

  const name = typeof unit?.name === 'string' ? unit.name.trim() : ''
  if (!name) {
    throw new Error('Unit name is required')
  }

  const physical = ensurePhysicalUnitName(name)

  const [changes] = await models.unit.update(
    {
      name,
      symbol: physical.symbol,
      unit_type: physical.unitType,
      to_grams_factor: physical.toGramsFactor,
      to_ml_factor: physical.toMlFactor,
    },
    {
      where: { id: unitId },
    },
  )

  return changes
}

async function deleteUnit(id) {
  const unitId = Number(id)
  if (!Number.isInteger(unitId) || unitId <= 0) {
    throw new Error('Unit id is invalid')
  }

  return models.unit.destroy({ where: { id: unitId } })
}

export default {
  getUnits,
  addUnit,
  updateUnit,
  deleteUnit,
}
