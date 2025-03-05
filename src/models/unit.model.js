import { DataTypes } from 'sequelize';
import db from '../db/sequelize.js';

const UnitModel = db.sequelize.define('Unit', {
  name: {
    type: DataTypes.STRING,
    allowNull: false
  }
});

export default UnitModel;
