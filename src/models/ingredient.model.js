import { DataTypes } from 'sequelize'
import db from '../db/sequelize.js';

const Ingredient = db.sequelize.define('Ingredient', {
  name: {
    type: DataTypes.STRING,
    allowNull: false
  },
  comment: {
    type: DataTypes.STRING
  },
  unit_id: {
    type: DataTypes.INTEGER,
    allowNull: false
  },
  quantity_per_package: {
    type: DataTypes.FLOAT
  },
  calories_per_100g: {
    type: DataTypes.FLOAT
  },
  carbohydrates_per_100g: {
    type: DataTypes.FLOAT
  },
  sugars_per_100g: {
    type: DataTypes.FLOAT
  },
  fat_per_100g: {
    type: DataTypes.FLOAT
  },
  protein_per_100g: {
    type: DataTypes.FLOAT
  },
  fiber_per_100g: {
    type: DataTypes.FLOAT
  }
});

export default Ingredient
