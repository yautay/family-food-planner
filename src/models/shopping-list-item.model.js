import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const ShoppingListItemModel = sequelize.define(
  'ShoppingListItem',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    shopping_list_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    product_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    custom_name: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    quantity: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    unit_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    is_checked: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 0,
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
    tableName: 'shopping_list_items',
    timestamps: false,
  },
)

export default ShoppingListItemModel
