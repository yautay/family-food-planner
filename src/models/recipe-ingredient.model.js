import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const RecipeIngredientModel = sequelize.define(
  'RecipeIngredient',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    recipe_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    product_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    ingredient_package_conversion_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
  },
  {
    tableName: 'recipe_ingredients',
    timestamps: false,
  },
)

export default RecipeIngredientModel
