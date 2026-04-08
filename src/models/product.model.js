import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const ProductModel = sequelize.define(
  'Product',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    normalized_name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    default_unit_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
  },
  {
    tableName: 'products',
    timestamps: false,
  },
)

export default ProductModel
