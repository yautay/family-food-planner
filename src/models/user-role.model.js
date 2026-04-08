import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const UserRoleModel = sequelize.define(
  'UserRole',
  {
    user_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
      primaryKey: true,
    },
    role_id: {
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
    tableName: 'user_roles',
    timestamps: false,
  },
)

export default UserRoleModel
