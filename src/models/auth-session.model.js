import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const AuthSessionModel = sequelize.define(
  'AuthSession',
  {
    id: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
    },
    user_id: {
      type: DataTypes.INTEGER,
      allowNull: false,
    },
    token_hash: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    expires_at: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    created_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    last_seen_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    revoked_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'auth_sessions',
    timestamps: false,
  },
)

export default AuthSessionModel
