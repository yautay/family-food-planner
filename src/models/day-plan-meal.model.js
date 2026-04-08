import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const DayPlanMealModel = sequelize.define(
  'DayPlanMeal',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    day_plan_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    recipe_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    servings: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    portions: {
      type: DataTypes.FLOAT,
      allowNull: false,
      defaultValue: 1,
    },
    note: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: '',
    },
    meal_order: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    updated_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'day_plan_meals',
    timestamps: false,
  },
)

export default DayPlanMealModel
