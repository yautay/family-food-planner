import tagController from './tag.controller.js';
import unitController from './unit.controller.js'
import ingredientController from './ingredient.controller.js'


const controllers = {};


controllers.tag = tagController;
controllers.unit = unitController;
controllers.ingredient = ingredientController;

export default controllers; // Corrected the export statement
