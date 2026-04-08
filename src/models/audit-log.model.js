import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const AuditLogModel = sequelize.define(
  'AuditLog',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    actor_user_id: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    action: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    target_type: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    target_id: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    meta_json: {
      type: DataTypes.STRING,
      allowNull: false,
      defaultValue: '{}',
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'audit_logs',
    timestamps: false,
  },
)

export default AuditLogModel
