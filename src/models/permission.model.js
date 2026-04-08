import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const PermissionModel = sequelize.define(
  'Permission',
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
    tableName: 'permissions',
    timestamps: false,
  },
)

export default PermissionModel
