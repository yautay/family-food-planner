import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const MealPlanEntryModel = sequelize.define(
  'MealPlanEntry',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    meal_plan_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    planned_date: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    meal_slot: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    recipe_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    custom_name: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    servings: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    note: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: '',
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'meal_plan_entries',
    timestamps: false,
  },
)

export default MealPlanEntryModel
