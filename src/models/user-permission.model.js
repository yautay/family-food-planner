import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const UserPermissionModel = sequelize.define(
  'UserPermission',
  {
    user_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    permission_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    allow: {
      type: DataTypes.INTEGER,
      allowNull: false,
      defaultValue: 1,
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'user_permissions',
    timestamps: false,
  },
)

export default UserPermissionModel
