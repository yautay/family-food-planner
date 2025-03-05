import models from '../models/index.js';

async function getIngredients() {
  return await models.ingredient.findAll();
}

async function addIngredient(item) {
  return models.ingredient.create(item)
}

async function updateIngredient(item) {
  return await models.ingredient.update(item, {
    where: { id: item.id }
  });
}

async function deleteIngredient(id) {
  return await models.ingredient.destroy({
    where: { id }
  });
}

export default {
  getIngredients,
  addIngredient,
  updateIngredient,
  deleteIngredient,
}
