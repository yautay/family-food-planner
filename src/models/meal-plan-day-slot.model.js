import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const MealPlanDaySlotModel = sequelize.define(
  'MealPlanDaySlot',
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
    day_plan_id: {
      type: DataTypes.INTEGER,
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
    updated_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'meal_plan_day_slots',
    timestamps: false,
  },
)

export default MealPlanDaySlotModel
