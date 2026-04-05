import { DataTypes } from 'sequelize'
import sequelize from '../db/client.js'

const TagModel = sequelize.define('Tag', {
  name: {
    type: DataTypes.STRING,
    allowNull: false,
  },
})

export default TagModel
