import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const IngredientPackageConversionModel = sequelize.define(
  'IngredientPackageConversion',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    product_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    package_type_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    grams_per_package: {
      type: DataTypes.FLOAT,
      allowNull: false,
    },
    source: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: 'manual',
    },
    samples_count: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 1,
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
    tableName: 'ingredient_package_conversions',
    timestamps: false,
  },
)

export default IngredientPackageConversionModel
