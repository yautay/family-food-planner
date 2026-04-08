import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const ShoppingListModel = sequelize.define(
  'ShoppingList',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    owner_user_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    meal_plan_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    status: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: 'open',
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
    tableName: 'shopping_lists',
    timestamps: false,
  },
)

export default ShoppingListModel
