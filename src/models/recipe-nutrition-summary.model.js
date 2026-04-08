import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const RecipeNutritionSummaryModel = sequelize.define(
  'RecipeNutritionSummary',
  {
    recipe_id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      allowNull: false,
    },
    total_grams: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    calories: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    carbohydrates: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    sugars: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    fat: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    protein: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    fiber: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
  },
  {
    tableName: 'recipe_nutrition_summary',
    timestamps: false,
  },
)

export default RecipeNutritionSummaryModel
