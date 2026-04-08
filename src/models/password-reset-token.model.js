import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const PasswordResetTokenModel = sequelize.define(
  'PasswordResetToken',
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
    used_at: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'password_reset_tokens',
    timestamps: false,
  },
)

export default PasswordResetTokenModel
