import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const RolePermissionModel = sequelize.define(
  'RolePermission',
  {
    role_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    permission_id: {
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
    tableName: 'role_permissions',
    timestamps: false,
  },
)

export default RolePermissionModel
