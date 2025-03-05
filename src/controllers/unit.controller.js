import models from '../models/index.js';

async function getUnits() {
  return await models.unit.findAll();
}

async function addUnit(unit) {
  return models.unit.create(unit)
}

async function updateUnit(unit) {
  return await models.unit.update(unit, {
    where: { id: unit.id }
  });
}

async function deleteUnit(id) {
  return await models.unit.destroy({
    where: { id }
  });
}

export default {
  getUnits,
  addUnit,
  updateUnit,
  deleteUnit,
}
