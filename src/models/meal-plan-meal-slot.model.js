import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const MealPlanMealSlotModel = sequelize.define(
  'MealPlanMealSlot',
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
    slot_name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    slot_time: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    sort_order: {
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
    tableName: 'meal_plan_meal_slots',
    timestamps: false,
  },
)

export default MealPlanMealSlotModel
