import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const ProductTagModel = sequelize.define(
  'ProductTag',
  {
    product_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    tag_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'product_tags',
    timestamps: false,
  },
)

export default ProductTagModel
