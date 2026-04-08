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
    default_package_type_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    comment: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: '',
    },
    quantity_per_package: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    unit_to_ml: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    calories_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    carbohydrates_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    sugars_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    fat_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    protein_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    fiber_per_100g: {
      type: DataTypes.FLOAT,
      allowNull: true,
    },
    nutrition_source: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    nutrition_updated_at: {
      type: DataTypes.STRING,
      allowNull: true,
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
    tableName: 'products',
    timestamps: false,
  },
)

export default ProductModel
