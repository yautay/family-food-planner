import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const RoleModel = sequelize.define(
  'Role',
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
    description: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: '',
    },
  },
  {
    tableName: 'roles',
    timestamps: false,
  },
)

export default RoleModel
