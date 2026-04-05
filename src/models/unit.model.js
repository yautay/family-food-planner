import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const UnitModel = sequelize.define('Unit', {
  name: {
    type: DataTypes.STRING,
    allowNull: false,
  },
})

export default UnitModel
