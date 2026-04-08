import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const RecipeModel = sequelize.define(
  'Recipe',
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
    source_file: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    instructions: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    owner_user_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    is_system: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 0,
    },
    is_editable: {
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
    tableName: 'recipes',
    timestamps: false,
  },
)

export default RecipeModel
