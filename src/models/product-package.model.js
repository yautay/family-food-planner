import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const ProductPackageModel = sequelize.define(
  'ProductPackage',
  {
    product_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    package_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    grams: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    is_default: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 0,
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'product_packages',
    timestamps: false,
  },
)

export default ProductPackageModel
